from __future__ import annotations

import json
from pathlib import Path

import pytest

from geo_research.parsers.serp.features import (
    feature_capability,
    parse_serp_features,
)
from geo_research.parsers.serp.service import SERPParseInput, parse_serp_response

FIXTURES = Path(__file__).parents[1] / "fixtures" / "serp"


def parse_fixture(engine: str, name: str = "organic"):
    return parse_serp_response(
        SERPParseInput(
            query_id="query-001",
            provider="dataforseo",
            search_engine=engine,
            search_type="organic",
            location_code="2840",
            language_code="en",
            device="desktop",
            collection_window="2026-09-25",
            response_id="response-001",
            source_ingestion_id="run-001",
            raw_file_hash="fixture-raw-hash",
            response_payload=json.loads(
                (FIXTURES / f"{engine}_{name}.json").read_text(encoding="utf-8")
            ),
        )
    )


@pytest.mark.parametrize("engine", ["google", "bing", "yahoo"])
def test_organic_feature_reconciles_each_enabled_engine_fixture(engine: str) -> None:
    parsed = parse_fixture(engine)
    features = parse_serp_features(parsed)

    assert len(features.organic_results) == 1
    result = features.organic_results[0]
    assert result.parent_serp_item_id == parsed.items[0].serp_item_id
    assert result.observation_id == parsed.observation.observation_id
    assert result.provider == "dataforseo"
    assert result.search_engine == engine
    assert result.feature_supported is True
    assert result.feature_observed is True
    assert result.engine_rank == 1
    assert result.normalized_rank == 1
    assert result.raw_evidence == parsed.items[0].raw_item_json


@pytest.mark.parametrize("engine", ["google", "bing", "yahoo"])
def test_enabled_organic_feature_keeps_supported_distinct_from_not_observed(
    engine: str,
) -> None:
    parsed = parse_fixture(engine, "empty_items")
    features = parse_serp_features(parsed)
    capability = feature_capability(engine, "organic", features.organic_results)

    assert features.organic_results == ()
    assert capability.feature_supported is True
    assert capability.feature_observed is False


@pytest.mark.parametrize(
    "feature", ["paid", "local", "questions", "related_queries", "images"]
)
def test_features_without_fixture_evidence_remain_unsupported(feature: str) -> None:
    capability = feature_capability("google", feature, ())

    assert capability.feature_supported is False
    assert capability.feature_observed is False


def test_organic_keys_are_deterministic_and_unique_at_parent_grain() -> None:
    first = parse_serp_features(parse_fixture("google")).organic_results[0]
    second = parse_serp_features(parse_fixture("google")).organic_results[0]

    assert first.organic_result_id == second.organic_result_id
    assert first.organic_result_id != first.parent_serp_item_id


def test_organic_item_count_reconciles_with_phase8_organic_items() -> None:
    parsed = parse_fixture("google")
    features = parse_serp_features(parsed)

    assert len(features.organic_results) == sum(
        item.normalized_item_type == "organic" for item in parsed.items
    )


def test_bing_does_not_use_google_feature_capabilities() -> None:
    parsed = parse_fixture("bing", "google_shaped")
    features = parse_serp_features(parsed)

    assert features.organic_results == ()
    assert feature_capability("bing", "paid", ()).feature_supported is False
