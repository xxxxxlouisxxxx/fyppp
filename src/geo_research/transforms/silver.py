"""Bronze raw_files to Silver parse-and-persist orchestration.

This job never calls APIs, never maps brands, and never computes SOV. SERP
payloads are unwrapped so parsers see a top-level `tasks` envelope. LLM
payloads are flattened with the existing llm_raw transformer only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from geo_research.parsers.serp.features import parse_serp_features
from geo_research.parsers.serp.service import (
    SERPParseInput,
    parse_serp_response,
    supported_serp_engines,
)
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.repositories import (
    SilverLLMObservation,
    SilverLLMRepository,
    SilverSERPFeatureRepository,
    SilverSERPRepository,
)
from geo_research.transforms.llm_raw import transform_llm_raw_payload

_DEFAULT_SEARCH_TYPE = "organic"
_DEFAULT_LOCATION_CODE = "2840"
_DEFAULT_LANGUAGE_CODE = "en"
_DEFAULT_DEVICE = "desktop"
_LLM_PARSER_NAME = "llm_raw_flatten"
_LLM_PARSER_VERSION = "1"
_PERSIST_BATCH_SIZE = 100


@dataclass(frozen=True, slots=True)
class SilverTransformReport:
    """Counts from one Bronze-to-Silver transform run."""

    serp_candidates: int
    serp_parsed: int
    serp_skipped_unsupported_engine: int
    serp_quarantined_payload: int
    serp_missing_raw: int
    llm_candidates: int
    llm_parsed: int
    llm_quarantined: int
    llm_missing_raw: int


def transform_bronze_to_silver(
    database: DuckDBStore,
    raw_root: Path,
) -> SilverTransformReport:
    """Parse Bronze response files into Silver tables without mutating raw JSON."""
    database.initialize()
    serp_rows, llm_rows = _candidate_response_rows(database)
    serp_report = _transform_serp_rows(database, raw_root, serp_rows)
    llm_report = _transform_llm_rows(database, raw_root, llm_rows)
    return SilverTransformReport(
        serp_candidates=len(serp_rows),
        serp_parsed=serp_report["parsed"],
        serp_skipped_unsupported_engine=serp_report["skipped_unsupported_engine"],
        serp_quarantined_payload=serp_report["quarantined_payload"],
        serp_missing_raw=serp_report["missing_raw"],
        llm_candidates=len(llm_rows),
        llm_parsed=llm_report["parsed"],
        llm_quarantined=llm_report["quarantined"],
        llm_missing_raw=llm_report["missing_raw"],
    )


def _candidate_response_rows(
    database: DuckDBStore,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    query = """
        SELECT
            raw_files.raw_file_id,
            raw_files.request_id,
            raw_files.raw_directory,
            raw_files.relative_path,
            raw_files.sha256,
            requests.source_category,
            requests.provider,
            requests.search_engine,
            requests.platform,
            requests.model_name,
            requests.query_id,
            requests.collection_window,
            requests.run_id,
            responses.response_id
        FROM bronze.raw_files AS raw_files
        JOIN bronze.api_requests AS requests
          ON requests.request_id = raw_files.request_id
        LEFT JOIN bronze.api_responses AS responses
          ON responses.request_id = raw_files.request_id
                LEFT JOIN silver.silver_search_observations AS serp_observations
                    ON serp_observations.response_id = responses.response_id
                LEFT JOIN silver.silver_llm_observations AS llm_observations
                    ON llm_observations.response_id = responses.response_id
        WHERE raw_files.artifact_type = 'response'
                    AND (
                            (requests.source_category = 'serp'
                                AND serp_observations.observation_id IS NULL)
                            OR (requests.source_category = 'llm'
                                AND llm_observations.observation_id IS NULL)
                    )
        ORDER BY raw_files.raw_file_id
    """
    with database.transaction() as connection:
        result = connection.execute(query)
        rows = result.fetchall()
        columns = [column[0] for column in result.description]
    mapped = [dict(zip(columns, row, strict=True)) for row in rows]
    serp_rows = [row for row in mapped if row["source_category"] == "serp"]
    llm_rows = [row for row in mapped if row["source_category"] == "llm"]
    return serp_rows, llm_rows


def _transform_serp_rows(
    database: DuckDBStore,
    raw_root: Path,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    counts = {
        "parsed": 0,
        "skipped_unsupported_engine": 0,
        "quarantined_payload": 0,
        "missing_raw": 0,
    }
    serp_repository = SilverSERPRepository(database)
    feature_repository = SilverSERPFeatureRepository(database)
    parsed_batch = []
    feature_batch = []
    for row in rows:
        payload = _load_json_artifact(raw_root, row)
        if payload is None:
            counts["missing_raw"] += 1
            continue
        engine = _string_or_default(row.get("search_engine"), "").casefold()
        if engine not in supported_serp_engines():
            counts["skipped_unsupported_engine"] += 1
            continue
        parse_input = SERPParseInput(
            query_id=_string_or_default(row.get("query_id"), row["request_id"]),
            provider=_string_or_default(row.get("provider"), "dataforseo"),
            search_engine=engine,
            search_type=_search_type_from_payload(payload),
            location_code=_location_code_from_payload(payload),
            language_code=_language_code_from_payload(payload),
            device=_device_from_payload(payload),
            collection_window=_string_or_default(
                row.get("collection_window"), "unknown"
            ),
            response_id=_string_or_default(
                row.get("response_id"), f"{row['request_id']}-response"
            ),
            source_ingestion_id=_string_or_default(
                row.get("run_id"), row["request_id"],
            ),
            raw_file_hash=_string_or_default(row.get("sha256"), ""),
            response_payload=_unwrap_serp_payload(payload),
        )
        parsed = parse_serp_response(parse_input)
        parsed_batch.append(parsed)
        feature_batch.append(parse_serp_features(parsed))
        if len(parsed_batch) == _PERSIST_BATCH_SIZE:
            serp_repository.record_many(parsed_batch)
            feature_repository.record_many(feature_batch)
            parsed_batch.clear()
            feature_batch.clear()
        counts["parsed"] += 1
        if parsed.quarantine:
            counts["quarantined_payload"] += 1
    if parsed_batch:
        serp_repository.record_many(parsed_batch)
        feature_repository.record_many(feature_batch)
    return counts


def _transform_llm_rows(
    database: DuckDBStore,
    raw_root: Path,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    counts = {"parsed": 0, "quarantined": 0, "missing_raw": 0}
    repository = SilverLLMRepository(database)
    observation_batch = []
    for row in rows:
        payload = _load_json_artifact(raw_root, row)
        if payload is None:
            counts["missing_raw"] += 1
            continue
        quarantined = False
        try:
            flattened = transform_llm_raw_payload(payload)
        except ValueError:
            flattened = _quarantine_llm_payload(payload)
            quarantined = True
            counts["quarantined"] += 1
        else:
            counts["parsed"] += 1
        observation_batch.append(
            _llm_observation(row, flattened, quarantined=quarantined)
        )
        if len(observation_batch) == _PERSIST_BATCH_SIZE:
            repository.record_many(observation_batch)
            observation_batch.clear()
    if observation_batch:
        repository.record_many(observation_batch)
    return counts


def _llm_observation(
    row: dict[str, Any],
    flattened: Mapping[str, Any],
    *,
    quarantined: bool,
) -> SilverLLMObservation:
    request_id = str(row["request_id"])
    response_id = _string_or_default(row.get("response_id"), f"{request_id}-response")
    raw_file_hash = _string_or_default(row.get("sha256"), "")
    items = flattened.get("items") or []
    citations = flattened.get("citations") or []
    outcome = (
        "quarantined"
        if quarantined or flattened.get("outcome_status") == "quarantined"
        else "available"
        if items
        else "no_results"
    )
    observation_id = str(
        uuid5(NAMESPACE_URL, f"{request_id}|{response_id}|{raw_file_hash}|llm")
    )
    location = flattened.get("location_code")
    return SilverLLMObservation(
        observation_id=observation_id,
        request_id=request_id,
        response_id=response_id,
        provider=_string_or_default(flattened.get("provider"), row.get("provider")),
        platform=_string_or_default(
            flattened.get("platform"), row.get("platform"), default="unknown"
        ),
        model_name=_string_or_default(
            flattened.get("model"), row.get("model_name"), default="unknown"
        ),
        query_text=_optional_string(flattened.get("query")),
        task_id=_optional_string(flattened.get("task_id")),
        status_code=_optional_int(flattened.get("status_code")),
        cost=_optional_float(flattened.get("cost")),
        language_code=_optional_string(flattened.get("language_code")),
        location_code=str(location) if location not in (None, "") else None,
        items_count=int(flattened.get("items_count") or len(items) or 0),
        response_text=_optional_string(flattened.get("response_text")),
        items_json=_json(items),
        citations_json=_json(citations),
        raw_file_hash=raw_file_hash,
        parser_name=_LLM_PARSER_NAME,
        parser_version=_LLM_PARSER_VERSION,
        outcome_status=outcome,
    )


def _quarantine_llm_payload(payload: object) -> dict[str, Any]:
    return {
        "provider": "dataforseo",
        "platform": "unknown",
        "model": "unknown",
        "query": None,
        "task_id": None,
        "status_code": None,
        "cost": None,
        "language_code": None,
        "location_code": None,
        "items_count": 0,
        "items": [],
        "citations": [],
        "response_text": None,
        "outcome_status": "quarantined",
        "raw_payload_preview": _json(payload)[:2000],
    }


def _load_json_artifact(raw_root: Path, row: Mapping[str, Any]) -> object | None:
    relative_path = Path(str(row["relative_path"]))
    candidates = [
        Path(str(row["raw_directory"])) / relative_path.name,
        raw_root / relative_path,
        Path(str(row["raw_directory"])) / relative_path,
    ]
    for path in candidates:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return None


def _unwrap_serp_payload(payload: object) -> object:
    if not isinstance(payload, Mapping):
        return payload
    for key in ("retrieval", "post", "get"):
        nested = payload.get(key)
        if isinstance(nested, Mapping) and "tasks" in nested:
            return nested
    return payload


def _task_data(payload: object) -> Mapping[str, Any]:
    unwrapped = _unwrap_serp_payload(payload)
    if not isinstance(unwrapped, Mapping):
        return {}
    tasks = unwrapped.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], Mapping):
        return {}
    data = tasks[0].get("data")
    return data if isinstance(data, Mapping) else {}


def _search_type_from_payload(payload: object) -> str:
    data = _task_data(payload)
    return _string_or_default(data.get("se_type"), _DEFAULT_SEARCH_TYPE)


def _location_code_from_payload(payload: object) -> str:
    data = _task_data(payload)
    return _string_or_default(data.get("location_code"), _DEFAULT_LOCATION_CODE)


def _language_code_from_payload(payload: object) -> str:
    data = _task_data(payload)
    return _string_or_default(data.get("language_code"), _DEFAULT_LANGUAGE_CODE)


def _device_from_payload(payload: object) -> str:
    data = _task_data(payload)
    return _string_or_default(data.get("device"), _DEFAULT_DEVICE)


def _string_or_default(*values: object, default: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return default


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
