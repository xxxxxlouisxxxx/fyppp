"""Fixture-proven engine-aware SERP feature models."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from geo_research.parsers.serp.contracts import SERPItem, SERPParseResult

_SUPPORTED_FEATURES: dict[str, frozenset[str]] = {
    "google": frozenset({"organic"}),
    "bing": frozenset({"organic"}),
    "yahoo": frozenset({"organic"}),
}


@dataclass(frozen=True, slots=True)
class FeatureCapability:
    search_engine: str
    feature_name: str
    feature_supported: bool
    feature_observed: bool


@dataclass(frozen=True, slots=True)
class OrganicResult:
    organic_result_id: str
    provider: str
    search_engine: str
    search_type: str
    observation_id: str
    parent_serp_item_id: str
    source_item_type: str | None
    feature_supported: bool
    feature_observed: bool
    normalization_status: str
    raw_evidence: str
    engine_rank: int
    normalized_rank: int
    raw_url: str | None
    canonical_url: str | None
    title: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class SERPFeatureResult:
    organic_results: tuple[OrganicResult, ...]


def parse_serp_features(parsed: SERPParseResult) -> SERPFeatureResult:
    """Create only organic rows supported by the parsed engine's verified fixtures."""
    observation = parsed.observation
    if not _is_supported(observation.search_engine, "organic"):
        return SERPFeatureResult(())
    results = tuple(
        _organic_result(parsed, item)
        for item in parsed.items
        if item.normalized_item_type == "organic" and item.rank_absolute is not None
    )
    return SERPFeatureResult(results)


def feature_capability(
    search_engine: str, feature_name: str, records: tuple[object, ...]
) -> FeatureCapability:
    """Separate fixture-proven support from whether this response observed it."""
    return FeatureCapability(
        search_engine=search_engine.casefold(),
        feature_name=feature_name,
        feature_supported=_is_supported(search_engine, feature_name),
        feature_observed=bool(records),
    )


def _organic_result(parsed: SERPParseResult, item: SERPItem) -> OrganicResult:
    observation = parsed.observation
    normalized_rank = item.rank_absolute
    if normalized_rank is None:
        raise ValueError("Organic feature rows require a positive rank_absolute")
    return OrganicResult(
        organic_result_id=str(
            uuid5(NAMESPACE_URL, f"{item.serp_item_id}|organic|{item.item_index}")
        ),
        provider=observation.provider,
        search_engine=observation.search_engine,
        search_type=observation.search_type,
        observation_id=observation.observation_id,
        parent_serp_item_id=item.serp_item_id,
        source_item_type=item.raw_item_type,
        feature_supported=True,
        feature_observed=True,
        normalization_status=item.normalization_status,
        raw_evidence=item.raw_item_json,
        engine_rank=normalized_rank,
        normalized_rank=normalized_rank,
        raw_url=item.raw_url,
        canonical_url=item.canonical_url,
        title=item.title,
        description=item.description,
    )


def _is_supported(search_engine: str, feature_name: str) -> bool:
    engine_features = _SUPPORTED_FEATURES.get(search_engine.casefold(), frozenset())
    return feature_name in engine_features
