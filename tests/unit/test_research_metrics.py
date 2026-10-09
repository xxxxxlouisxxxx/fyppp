"""Research contracts and atomic historical snapshot integration, fixture only."""

from __future__ import annotations

import copy
import hashlib
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from geo_research.dashboard.data import load_snapshot, research_summary
from geo_research.domain.comparisons import Comparison
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.releases import ReleaseRepository
from geo_research.storage.reviews import append_review, history
from geo_research.transforms.feature_evidence import (
    TABLES,
    enrich_features,
    export_candidate_review,
    persist_features,
)
from geo_research.transforms.research_metrics import measure_features
from tests.unit.test_releases import _seed_complete_gold
from tests.unit.test_response_evidence import ROOT, context, payload, registry


def approved_registry():
    value = registry()
    for brand in value["brands"].values():
        brand.update(active=True, ownership_type="competitor")
    return value


def measured(value, category="llm", status="available", reg=None):
    reg = reg or approved_registry()
    evidence = enrich_features(context(category, status), value, reg)
    return measure_features(evidence, reg), evidence


def feature(rows, name, brand="nike"):
    return next(row for row in rows
                if row["feature"] == name and row["brand_id"] == brand)


def test_occurrences_unique_share_and_presence_denominators():
    rows, _ = measured(payload([{
        "type": "gemini_text", "original_text": "Nike Nike", "sources": [
            {"url": "https://nike.com/a"}, {"url": "https://nike.com/a#x"},
            {"url": "https://other.com/a"},
        ],
    }]))
    answer = feature(rows, "answer_text")
    assert answer["observed_brand_count"] == 2
    assert answer["share"] is None and answer["share_denominator"] is None
    assert (answer["presence_numerator"], answer["presence_denominator"]) == (1, 1)
    citation = feature(rows, "citation")
    assert (citation["share_numerator"], citation["share_denominator"]) == (1, 2)
    assert citation["share"] == .5
    assert {row["quality_status"] for row in rows} == {"experimental"}


def test_partial_positive_not_a_negative_capable_sample():
    value = payload([{
        "type": "gemini_text", "original_text": "Nike", "sources": None,
    }])
    rows, _ = measured(value)
    citation = feature(rows, "citation")
    assert citation["presence"] is None
    assert citation["presence_denominator"] is None
    assert citation["share"] is None
    value["retrieval"]["tasks"][0]["result"][0]["items"][0]["extra"] = {"new": "x"}
    rows, _ = measured(value)
    answer = feature(rows, "answer_text")
    assert answer["presence"] == 1 and answer["presence_denominator"] is None


@pytest.mark.parametrize(
    "status", ["pending", "provider_error", "missing", "quarantined"],
)
def test_unavailable_is_null_not_zero(status):
    rows, _ = measured(None, status=status)
    assert rows
    assert all(row["observed_brand_count"] is None
               and row["presence"] is None and row["share"] is None for row in rows)


def test_empty_complete_feature_zero_presence_undefined_share():
    value = payload([])
    value["retrieval"]["tasks"][0]["result"][0]["markdown"] = None
    rows, _ = measured(value)
    answer = feature(rows, "answer_text")
    assert (answer["presence"], answer["presence_denominator"]) == (0, 1)
    assert feature(rows, "citation")["share"] is None


def test_candidates_missing_dates_and_ambiguous_ownership_excluded():
    reg = approved_registry()
    reg["brands"]["air"]["review_status"] = "candidate"
    reg["domains"].append({"brand_id": "air", "domain": "nike.com"})
    value = payload([{
        "type": "organic", "url": "https://nike.com/a", "rank_group": 1,
    }])
    rows, _ = measured(value, "serp", reg=reg)
    assert not any(row["brand_id"] == "air" for row in rows)
    reg["brands"]["air"]["review_status"] = "approved"
    rows, _ = measured(value, "serp", reg=reg)
    organic = feature(rows, "organic")
    assert organic["ambiguous_entities"] == 1
    assert organic["share"] == 0 and organic["presence"] == 1
    evidence = enrich_features(context(), payload([]), reg)
    evidence[TABLES[0]][0]["collected_at"] = None
    assert measure_features(evidence, reg) == []


def seed_research(database):
    with database.transaction() as connection:
        connection.execute("""
            CREATE TABLE bronze.brand_registry (
                brand_id VARCHAR, canonical_name VARCHAR, ownership_type VARCHAR,
                market VARCHAR, language VARCHAR, effective_start_date DATE,
                effective_end_date DATE, active BOOLEAN, recorded_at TIMESTAMPTZ
            )
        """)
        connection.execute("""
            INSERT INTO bronze.brand_registry VALUES
            ('nike', 'Nike', 'competitor', 'HK', 'zh-TW',
             '2026-01-01', NULL, true, current_timestamp)
        """)
        for category, obs, instrument, raw_hash in (
            ("serp", "obs-serp-1", "query-001", "hash-1"),
            ("llm", "obs-llm-1", "prompt-001", "hash-llm-1"),
        ):
            ctx = context(category)
            ctx.update(
                observation_id=obs, query_id=instrument, raw_file_hash=raw_hash,
                response_id="response-1" if category == "serp" else "response-llm-1",
                engine_or_platform="google" if category == "serp" else "chatgpt",
            )
            value = payload([{
                "type": "chat_gpt_products", "items": [{"brand": "NewUnknownBrand"}],
            }]) if category == "llm" else payload([])
            value["retrieval"]["tasks"][0]["data"].update(
                language_code="zh-tw", location_code=2344,
            )
            persist_features(
                connection, enrich_features(ctx, value, approved_registry()),
            )
        connection.execute(
            "UPDATE analytics.gold_serp_brand_visibility SET language_code='zh-tw'"
        )
        connection.execute(
            "UPDATE analytics.gold_llm_brand_visibility SET language_code='zh-tw'"
        )


def mapping():
    return Comparison(
        comparison_id="comparison-001", query_id="query-001", prompt_id="prompt-001",
        active=True, mapping_version="fixture-1", reviewer="fixture reviewer",
        approval_date=date(2026, 10, 8), reason="fixture approval",
        effective_start_date=date(2026, 10, 8), effective_end_date=None,
        scope="matched_locale_window",
    )


def test_two_snapshots_readonly_ui_and_history(tmp_path, monkeypatch):
    database = DuckDBStore(tmp_path / "fixture.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    seed_research(database)
    publisher = ReleaseRepository(database)
    publisher.complete("one", research_comparisons=(mapping(),))
    first = load_snapshot(database.path)
    assert not first.research["coverage"].empty
    assert "query_text" not in first.research["coverage"]
    assert "query_text" not in first.research["metrics"]
    assert len(first.research["pairs"]) == 1
    assert first.research["candidates"].identity_name.tolist() == ["NewUnknownBrand"]
    assert set(first.research["metrics"].brand_id) == {"nike"}
    append_review(
        tmp_path / "review.sqlite", database.path, opportunity_id="fixture-opp",
        release_id="one", expected_sequence=0, status="new",
        classification="hypothesis", reviewer="fixture reviewer", reason="inspect",
        evidence=(first.research["candidates"].evidence_id.iloc[0],),
    )
    assert len(history(tmp_path / "review.sqlite")) == 1
    assert "raw_evidence_json" not in first.research["candidates"]
    summary = research_summary(first.research["metrics"])
    assert summary.presence_denominator.max() == 1
    with database.transaction() as connection:
        assert export_candidate_review(connection, tmp_path / "review.csv") == 1
        connection.execute("UPDATE bronze.brand_registry SET active=false")
    publisher.complete("two", research_comparisons=(mapping(),))
    assert load_snapshot(database.path).research["metrics"].empty
    assert len(load_snapshot(database.path, "one").research["metrics"]) == 10
    before = hashlib.sha256(database.path.read_bytes()).hexdigest()
    monkeypatch.setenv("GEO_DASHBOARD_DB", str(database.path))
    app = AppTest.from_file(str(ROOT / "streamlit_app.py")).run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 5
    assert hashlib.sha256(database.path.read_bytes()).hexdigest() == before


def test_research_mixed_hash_rolls_back_whole_release(tmp_path):
    database = DuckDBStore(tmp_path / "fixture.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    seed_research(database)
    publisher = ReleaseRepository(database)
    publisher.complete("old")
    with database.transaction() as connection:
        connection.execute(
            "UPDATE silver.evidence_results_v2 SET raw_file_hash='wrong'",
        )
    with pytest.raises(ValueError, match="hash differs"):
        publisher.complete("bad", research_comparisons=(mapping(),))
    assert publisher.current_release_id() == "old"
    assert "bad" not in load_snapshot(database.path).releases.release_id.tolist()


def test_summary_deduplicates_result_samples():
    import pandas as pd

    rows, _ = measured(payload([]))
    for row in rows:
        row["collection_window"] = "fixture"
    duplicated = pd.DataFrame(rows + copy.deepcopy(rows))
    summary = research_summary(duplicated)
    assert summary.results.max() == 1