from __future__ import annotations

import json
from pathlib import Path

import pytest

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
def test_verified_fixture_reconciles_to_traceable_top_level_items(engine: str) -> None:
    result = parse_fixture(engine)

    assert result.observation.observation_id
    assert result.observation.has_results is True
    assert result.observation.outcome_status == "available"
    assert len(result.items) == 1
    item = result.items[0]
    assert item.observation_id == result.observation.observation_id
    assert item.engine == engine
    assert item.response_id == "response-001"
    assert item.source_ingestion_id == "run-001"
    assert item.raw_file_hash == "fixture-raw-hash"
    assert item.rank_absolute == 1
    assert item.canonical_url == "https://example.test/path?source=fixture"
    assert item.raw_item_json


def test_observation_id_is_deterministic() -> None:
    assert parse_fixture("google").observation == parse_fixture("google").observation


def test_engine_parser_isolation_does_not_use_google_mapping_for_bing() -> None:
    result = parse_fixture("bing", "google_shaped")

    assert result.items == ()
    assert result.quarantine[0].reason == "malformed_item"
    assert result.quarantine[0].parser_name == "bing_organic"


@pytest.mark.parametrize("name", ["null_result", "empty_result"])
def test_null_and_empty_results_are_safe_no_result_observations(name: str) -> None:
    result = parse_fixture("google", name)

    assert result.observation.has_results is False
    assert result.observation.outcome_status == "no_results"
    assert result.items == ()
    assert result.quarantine == ()


def test_unknown_item_is_retained_and_quarantined() -> None:
    result = parse_fixture("google", "unknown_item")

    assert len(result.items) == 1
    assert result.items[0].normalized_item_type == "unknown"
    assert result.quarantine[0].reason == "unknown_item_type"


def test_malformed_item_is_quarantined_without_dropping_other_items() -> None:
    result = parse_fixture("google", "malformed_item")

    assert len(result.items) == 1
    assert result.quarantine[0].reason == "malformed_item"


def test_non_positive_rank_is_quarantined_and_preserved() -> None:
    result = parse_fixture("google", "invalid_rank")

    assert len(result.items) == 1
    assert result.items[0].rank_absolute is None
    assert result.quarantine[0].reason == "invalid_rank"
