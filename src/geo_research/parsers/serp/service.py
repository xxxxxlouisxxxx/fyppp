"""SERP parser dispatch, traceability, and conservative normalization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from geo_research.parsers.serp.base import OrganicSERPParser
from geo_research.parsers.serp.bing import BingOrganicParser
from geo_research.parsers.serp.contracts import (
    SearchObservation,
    SERPItem,
    SERPParseResult,
    SERPParsingQuarantine,
)
from geo_research.parsers.serp.google import GoogleOrganicParser
from geo_research.parsers.serp.yahoo import YahooOrganicParser

_PARSERS: dict[str, OrganicSERPParser] = {
    "google": GoogleOrganicParser(),
    "bing": BingOrganicParser(),
    "yahoo": YahooOrganicParser(),
}
_KNOWN_ITEM_TYPES = frozenset({"organic", "featured_snippet"})
SUPPORTED_SERP_ENGINES = frozenset(_PARSERS)


def supported_serp_engines() -> frozenset[str]:
    """Return engine keys with a fixture-proven organic parser."""
    return SUPPORTED_SERP_ENGINES


@dataclass(frozen=True, slots=True)
class SERPParseInput:
    query_id: str
    provider: str
    search_engine: str
    search_type: str
    location_code: str
    language_code: str
    device: str
    collection_window: str
    response_id: str
    source_ingestion_id: str
    raw_file_hash: str
    response_payload: object


def parse_serp_response(parse_input: SERPParseInput) -> SERPParseResult:
    """Parse one preserved response or retain every unsafe element in quarantine."""
    parser = _PARSERS.get(parse_input.search_engine.casefold())
    if parser is None:
        raise ValueError(f"Unsupported SERP parser: {parse_input.search_engine}")
    observation_id = _observation_id(parse_input)
    raw_items, has_results, payload_problem = _extract_items(
        parse_input.response_payload
    )
    outcome_status = "available" if has_results else "no_results"
    observation = SearchObservation(
        observation_id=observation_id,
        query_id=parse_input.query_id,
        provider=parse_input.provider,
        search_engine=parser.engine,
        search_type=parse_input.search_type,
        location_code=parse_input.location_code,
        language_code=parse_input.language_code,
        device=parse_input.device,
        collection_window=parse_input.collection_window,
        response_id=parse_input.response_id,
        source_ingestion_id=parse_input.source_ingestion_id,
        raw_file_hash=parse_input.raw_file_hash,
        has_results=has_results,
        outcome_status=outcome_status,
    )
    items: list[SERPItem] = []
    quarantine: list[SERPParsingQuarantine] = []
    if payload_problem is not None:
        quarantine.append(
            _quarantine(
                parse_input, observation_id, parser, None, payload_problem, None
            )
        )
    for item_index, raw_item in enumerate(raw_items):
        raw_item_json = _json(raw_item)
        if not isinstance(raw_item, dict):
            quarantine.append(
                _quarantine(
                    parse_input,
                    observation_id,
                    parser,
                    item_index,
                    "malformed_item",
                    raw_item_json,
                )
            )
            continue
        mapped = parser.parse_item(raw_item)
        if mapped is None:
            quarantine.append(
                _quarantine(
                    parse_input,
                    observation_id,
                    parser,
                    item_index,
                    "malformed_item",
                    raw_item_json,
                )
            )
            continue
        raw_type = mapped["raw_item_type"]
        normalized_type = raw_type if raw_type in _KNOWN_ITEM_TYPES else "unknown"
        warning: str | None = None
        if normalized_type == "unknown":
            warning = "unknown_item_type"
            quarantine.append(
                _quarantine(
                    parse_input,
                    observation_id,
                    parser,
                    item_index,
                    warning,
                    raw_item_json,
                )
            )
        rank_group = _positive_int(mapped["rank_group"])
        rank_absolute = _positive_int(mapped["rank_absolute"])
        if (mapped["rank_group"] is not None and rank_group is None) or (
            mapped["rank_absolute"] is not None and rank_absolute is None
        ):
            warning = _append_warning(warning, "invalid_rank")
            quarantine.append(
                _quarantine(
                    parse_input,
                    observation_id,
                    parser,
                    item_index,
                    "invalid_rank",
                    raw_item_json,
                )
            )
        raw_url = _string_or_none(mapped["url"])
        raw_domain = _string_or_none(mapped["domain"])
        items.append(
            SERPItem(
                serp_item_id=_item_id(observation_id, item_index, raw_item_json),
                observation_id=observation_id,
                engine=parser.engine,
                response_id=parse_input.response_id,
                source_ingestion_id=parse_input.source_ingestion_id,
                raw_file_hash=parse_input.raw_file_hash,
                item_index=item_index,
                raw_item_type=raw_type,
                normalized_item_type=normalized_type,
                rank_group=rank_group,
                rank_absolute=rank_absolute,
                page=None,
                position=rank_group,
                raw_domain=raw_domain,
                normalized_domain=_normalized_domain(raw_domain, raw_url),
                raw_url=raw_url,
                canonical_url=_canonical_url(raw_url),
                title=_string_or_none(mapped["title"]),
                description=_string_or_none(mapped["description"]),
                raw_item_json=raw_item_json,
                parser_name=parser.parser_name,
                parser_version=parser.parser_version,
                rank_semantics_version=parser.rank_semantics_version,
                normalization_status="normalized" if warning is None else "warning",
                parsing_warning=warning,
            )
        )
    return SERPParseResult(observation, tuple(items), tuple(quarantine))


def _extract_items(payload: object) -> tuple[list[object], bool, str | None]:
    if not isinstance(payload, dict):
        return [], False, "malformed_payload"
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        return [], False, "malformed_payload"
    results = tasks[0].get("result")
    if results is None or results == []:
        return [], False, None
    if not isinstance(results, list):
        return [], False, "malformed_result"
    items: list[object] = []
    for result in results:
        if not isinstance(result, dict):
            return [], False, "malformed_result"
        result_items = result.get("items")
        if result_items is None:
            continue
        if not isinstance(result_items, list):
            return [], False, "malformed_result"
        items.extend(result_items)
    return items, bool(items), None


def _observation_id(parse_input: SERPParseInput) -> str:
    dimensions = "|".join(
        (
            parse_input.query_id,
            parse_input.provider,
            parse_input.search_engine.casefold(),
            parse_input.search_type,
            parse_input.location_code,
            parse_input.language_code,
            parse_input.device,
            parse_input.collection_window,
        )
    )
    return str(uuid5(NAMESPACE_URL, dimensions))


def _item_id(observation_id: str, item_index: int, raw_item_json: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{observation_id}|{item_index}|{sha256(raw_item_json.encode()).hexdigest()}",
        )
    )


def _quarantine(
    parse_input: SERPParseInput,
    observation_id: str,
    parser: OrganicSERPParser,
    item_index: int | None,
    reason: str,
    raw_item_json: str | None,
) -> SERPParsingQuarantine:
    identifier = f"{observation_id}|{item_index}|{reason}|{raw_item_json}"
    return SERPParsingQuarantine(
        quarantine_id=str(uuid5(NAMESPACE_URL, identifier)),
        observation_id=observation_id,
        engine=parser.engine,
        response_id=parse_input.response_id,
        source_ingestion_id=parse_input.source_ingestion_id,
        raw_file_hash=parse_input.raw_file_hash,
        item_index=item_index,
        reason=reason,
        raw_item_json=raw_item_json,
        parser_name=parser.parser_name,
        parser_version=parser.parser_version,
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _positive_int(value: object) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _normalized_domain(raw_domain: str | None, raw_url: str | None) -> str | None:
    candidate = raw_domain or (urlsplit(raw_url).hostname if raw_url else None)
    return candidate.casefold().rstrip(".") if candidate else None


def _canonical_url(raw_url: str | None) -> str | None:
    if raw_url is None:
        return None
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path,
            parsed.query,
            "",
        )
    )


def _append_warning(current: str | None, extra: str) -> str:
    return extra if current is None else f"{current};{extra}"
