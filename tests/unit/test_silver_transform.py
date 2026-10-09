from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.raw_store import RawEvidence, RawStore
from geo_research.storage.repositories import RawEvidenceRepository
from geo_research.transforms.silver import transform_bronze_to_silver

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _google_payload(
    *, wrap_retrieval: bool = False, unknown_item: bool = False,
) -> dict:
    if unknown_item:
        payload = json.loads(
            (FIXTURES / "serp" / "google_unknown_item.json").read_text(encoding="utf-8")
        )
    else:
        payload = json.loads(
            (FIXTURES / "serp" / "google_organic.json").read_text(encoding="utf-8")
        )
    if wrap_retrieval:
        return {"retrieval": payload}
    return payload


def _llm_payload() -> dict:
    return json.loads(
        (FIXTURES / "llm" / "gemini_response.json").read_text(encoding="utf-8")
    )


def _seed(
    tmp_path: Path,
    *,
    request_id: str,
    source_category: str,
    platform_or_engine: str,
    response_payload: dict,
    query_id: str | None = "query-1",
) -> DuckDBStore:
    raw = RawStore(tmp_path / "raw")
    evidence = RawEvidence(
        source_category=source_category,
        provider="dataforseo",
        platform_or_engine=platform_or_engine,
        run_id="run-1",
        request_id=request_id,
        collected_at=datetime(2026, 9, 25, tzinfo=UTC),
        request_payload={"keyword": "example"},
        response_payload=response_payload,
        query_id=query_id,
        search_target_id="target-1",
        collection_window="2026-09-25",
        request_hash="request-hash",
        deduplication_key="dedupe-key",
    )
    result = raw.write(evidence)
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    RawEvidenceRepository(database, raw).record(evidence, result)
    return database


def test_serp_bronze_to_silver_parses_wrapped_google_payload(tmp_path: Path) -> None:
    database = _seed(
        tmp_path,
        request_id="serp-1",
        source_category="serp",
        platform_or_engine="google",
        response_payload=_google_payload(wrap_retrieval=True),
    )

    report = transform_bronze_to_silver(database, tmp_path / "raw")
    second = transform_bronze_to_silver(database, tmp_path / "raw")

    assert report.serp_candidates == 1
    assert report.serp_parsed == 1
    assert report.serp_skipped_unsupported_engine == 0
    assert second.serp_candidates == 0
    assert second.serp_parsed == 0
    with database.transaction() as connection:
        observations = connection.execute(
            "SELECT count(*) FROM silver.silver_search_observations"
        ).fetchone()[0]
        items = connection.execute(
            "SELECT count(*) FROM silver.silver_serp_items"
        ).fetchone()[0]
        organic = connection.execute(
            "SELECT count(*) FROM silver.silver_organic_results"
        ).fetchone()[0]
        has_results, outcome = connection.execute(
            "SELECT has_results, outcome_status FROM silver.silver_search_observations"
        ).fetchone()
    assert observations == 1
    assert items == 1
    assert organic == 1
    assert has_results is True
    assert outcome == "available"


def test_unknown_serp_item_is_quarantined_and_unsupported_engine_is_skipped(
    tmp_path: Path,
) -> None:
    raw = RawStore(tmp_path / "raw")
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    repository = RawEvidenceRepository(database, raw)
    for request_id, engine, payload in (
        (
            "serp-unknown-item",
            "google",
            _google_payload(unknown_item=True),
        ),
        (
            "serp-unsupported",
            "duckduckgo",
            _google_payload(),
        ),
    ):
        evidence = RawEvidence(
            source_category="serp",
            provider="dataforseo",
            platform_or_engine=engine,
            run_id="run-1",
            request_id=request_id,
            collected_at=datetime(2026, 9, 25, tzinfo=UTC),
            request_payload={"keyword": "example"},
            response_payload=payload,
            query_id="query-1",
            collection_window="2026-09-25",
        )
        repository.record(evidence, raw.write(evidence))

    report = transform_bronze_to_silver(database, tmp_path / "raw")

    assert report.serp_candidates == 2
    assert report.serp_parsed == 1
    assert report.serp_skipped_unsupported_engine == 1
    assert report.serp_quarantined_payload == 1
    with database.transaction() as connection:
        quarantine_reason = connection.execute(
            "SELECT reason FROM silver.silver_serp_parsing_quarantine"
        ).fetchone()[0]
        observation_count = connection.execute(
            "SELECT count(*) FROM silver.silver_search_observations"
        ).fetchone()[0]
    assert quarantine_reason == "unknown_item_type"
    assert observation_count == 1


def test_llm_flatten_is_persisted_without_guessed_item_schema(tmp_path: Path) -> None:
    database = _seed(
        tmp_path,
        request_id="llm-1",
        source_category="llm",
        platform_or_engine="gemini",
        response_payload=_llm_payload(),
        query_id=None,
    )

    report = transform_bronze_to_silver(database, tmp_path / "raw")

    assert report.llm_candidates == 1
    assert report.llm_parsed == 1
    assert report.llm_quarantined == 0
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT platform, items_count, outcome_status, parser_name, "
            "raw_file_hash FROM silver.silver_llm_observations"
        ).fetchone()
        items_json = connection.execute(
            "SELECT items_json FROM silver.silver_llm_observations"
        ).fetchone()[0]
    assert row[0] == "gemini"
    assert row[1] == 11
    assert row[2] == "available"
    assert row[3] == "llm_raw_flatten"
    assert row[4]
    assert '"item_type":"gemini_text"' in items_json


def test_malformed_llm_payload_is_quarantined(tmp_path: Path) -> None:
    database = _seed(
        tmp_path,
        request_id="llm-bad",
        source_category="llm",
        platform_or_engine="gemini",
        response_payload={"not": "an llm envelope"},
        query_id=None,
    )

    report = transform_bronze_to_silver(database, tmp_path / "raw")

    assert report.llm_parsed == 0
    assert report.llm_quarantined == 1
    with database.transaction() as connection:
        outcome = connection.execute(
            "SELECT outcome_status FROM silver.silver_llm_observations"
        ).fetchone()[0]
    assert outcome == "quarantined"
