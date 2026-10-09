"""Dashboard tests write exclusively to pytest temporary warehouses."""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import pytest

from geo_research.dashboard.data import (
    Filters,
    channel_rows,
    display,
    eligible_comparisons,
    filtered,
    load_snapshot,
    locale_summary,
    opportunities,
    presence_summary,
    source_statuses,
)
from geo_research.storage.migrations import MIGRATION_006, MIGRATION_007

ROOT = Path(__file__).resolve().parents[2]


def _insert(connection, table, values):
    fields = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO presentation.{table} ({fields}) VALUES ({placeholders})",
        list(values.values()),
    )


def _warehouse(path, *, legacy=False):
    with duckdb.connect(str(path)) as connection:
        connection.execute(MIGRATION_006)
        if not legacy:
            connection.execute(MIGRATION_007)
        for release_id, status in (("done", "completed"), ("unfinished", "incomplete")):
            _insert(connection, "releases", {
                "release_id": release_id, "status": status,
                "created_at": "2026-10-01T00:00:00Z",
                "completed_at": (
                    "2026-10-02T00:00:00Z" if status == "completed" else None
                ),
                "metric_version": "1.0.0", "completeness_json": "{}",
            })
        connection.execute(
            "INSERT INTO presentation.release_current VALUES ('current', 'done')"
        )
        context = {} if legacy else {
            "language_code": "en", "location_code": "2344", "collection_window": "w1",
        }
        for channel in ("serp", "llm"):
            for index, present in enumerate((1, 0, 1), start=1):
                common = {
                    "release_id": "done", "metric_id": f"{channel}-{index}",
                    "observation_id": f"{channel}-obs-{index}", "brand_id": "b1",
                    "brand_canonical_name": "Example", "provider": "dataforseo",
                    "source_category": channel, "metric_version": "1.0.0",
                    "numerator": present, "denominator": 10 if channel == "serp" else 1,
                    "metric_value": present / 10 if channel == "serp" else present,
                    "availability_status": (
                        "available" if index < 3 else "provider_error"
                    ),
                    "collection_status": (
                        "available" if index < 3 else "provider_error"
                    ),
                    **context,
                }
                if index == 3:
                    common["metric_value"] = None
                    if not legacy:
                        common["language_code"] = None
                        common["location_code"] = None
                if channel == "serp":
                    common.update({
                        "query_id": "q1", "search_engine": "google",
                        "search_type": "organic", "collection_window": "w1",
                        "metric_name": "serp_organic_sov",
                    })
                else:
                    common.update({
                        "prompt_id": "p1", "platform": "chatgpt", "model_name": "model",
                        "metric_name": "llm_brand_mention", "mention_count": present,
                        "citation_count": 0,
                    })
                _insert(connection, f"release_{channel}_brand_visibility", common)
                # A second brand must not double source observation counts.
                _insert(connection, f"release_{channel}_brand_visibility", {
                    **common, "metric_id": f"{channel}-{index}-b2", "brand_id": "b2",
                })
            _insert(connection, f"release_{channel}_brand_visibility", {
                **common, "release_id": "unfinished", "metric_id": f"{channel}-bad",
                "observation_id": "should-never-appear",
            })
        for index, (serp, llm) in enumerate(((1, 0), (0, 1), (0, 0), (1, 1))):
            row = {
                "release_id": "done", "metric_id": f"pair-{index}",
                "comparison_id": "c1", "query_id": "q1", "prompt_id": "p1",
                "brand_id": "b1", "brand_canonical_name": "Example",
                "metric_name": "comparison_brand_presence", "metric_version": "2.0.0",
                "serp_observation_id": f"s{index}", "llm_observation_id": f"l{index}",
                "serp_availability_status": "available",
                "llm_availability_status": "available",
                "serp_numerator": serp, "serp_denominator": 10,
                "serp_metric_value": serp / 10, "llm_numerator": llm,
                "llm_denominator": 1, "llm_metric_value": llm,
                "metric_value": llm - serp, "availability_status": "available",
            }
            if not legacy:
                row.update({
                    **context, "comparison_eligibility": "matched_context",
                    "search_engine": "google", "platform": "chatgpt",
                })
            _insert(connection, "release_comparison_brand_metrics", row)
        _insert(connection, "release_comparison_brand_metrics", {
            **row, "metric_id": "v1", "metric_name": "comparison_brand_visibility",
            "metric_version": "1.0.0", "metric_value": 0.9,
        })
    return path


@pytest.fixture
def warehouse(tmp_path):
    return _warehouse(tmp_path / "dashboard.duckdb")


def test_read_only_no_writes_and_fixed_release(warehouse, monkeypatch):
    before = hashlib.sha256(warehouse.read_bytes()).hexdigest()
    original = duckdb.connect
    seen = []

    def connect(*args, **kwargs):
        seen.append(kwargs)
        assert kwargs["read_only"] is True
        return original(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", connect)
    snapshot = load_snapshot(warehouse)
    assert snapshot.message is None
    assert snapshot.release["release_id"] == "done"
    assert all(set(f.release_id) == {"done"} for f in snapshot.frames.values())
    assert seen and hashlib.sha256(warehouse.read_bytes()).hexdigest() == before
    # Changing the pointer later cannot change the already materialized snapshot.
    with original(str(warehouse)) as c:
        c.execute("UPDATE presentation.release_current SET release_id='unfinished'")
    assert snapshot.release["release_id"] == "done"
    assert load_snapshot(warehouse).message.startswith("No valid completed current")
    assert load_snapshot(warehouse, "done").message is None
    assert load_snapshot(warehouse, "unfinished").frames == {}


def test_counts_and_available_denominators(warehouse):
    frames = load_snapshot(warehouse).frames
    summary = presence_summary(frames)
    assert len(summary) == 4
    assert summary.presence_rate.tolist() == [0.5] * 4
    assert summary.available.tolist() == [2] * 4
    assert summary.observations.tolist() == [3] * 4
    assert source_statuses(frames).observations.sum() == 6
    # Paired expansion never enters the channel presence calculation.
    frames["comparison"] = frames["comparison"].loc[
        frames["comparison"].index.repeat(5)
    ]
    assert presence_summary(frames).available.tolist() == [2] * 4
    assert [p["pairs"] for p in opportunities(frames["comparison"])] == [1, 1, 1]


def test_filters_unknown_empty_and_channel_local(warehouse):
    snapshot = load_snapshot(warehouse)
    frames = filtered(snapshot, Filters(engines=("bing",)))
    assert frames["serp"].empty and frames["comparison"].empty
    assert len(frames["llm"]) == 6
    frames = filtered(snapshot, Filters(platforms=("gemini",)))
    assert frames["llm"].empty and len(frames["serp"]) == 6
    frames = filtered(snapshot, Filters(languages=(None,), brands=("b1",)))
    assert len(frames["serp"]) == len(frames["llm"]) == 1
    assert frames["comparison"].empty
    assert filtered(snapshot, Filters(brands=()))["serp"].empty
    frames = filtered(snapshot, Filters(locations=("2344",), windows=("w1",)))
    assert len(frames["serp"]) == len(frames["llm"]) == 4
    assert "location=2344" in locale_summary(frames).locale.iloc[0]
    assert display(None) == "Unknown (not recorded)"


def test_malicious_values_are_not_sql(warehouse):
    attack = "done'; DROP TABLE presentation.releases; --"
    assert load_snapshot(warehouse, attack).message.startswith("Selected release")
    snapshot = load_snapshot(warehouse)
    assert filtered(snapshot, Filters(brands=(attack,)))["serp"].empty
    assert load_snapshot(warehouse).message is None


def test_legacy_context_and_v1_excluded(tmp_path):
    snapshot = load_snapshot(_warehouse(tmp_path / "legacy.duckdb", legacy=True))
    assert snapshot.message is None
    assert snapshot.frames["llm"].collection_window.isna().all()
    assert snapshot.frames["serp"].language_code.isna().all()
    assert eligible_comparisons(snapshot.frames["comparison"]).empty
    assert all(p["pairs"] == 0 for p in opportunities(snapshot.frames["comparison"]))
    assert not locale_summary(snapshot.frames).empty


def test_opportunities_require_available_known_v2_context(warehouse):
    frame = load_snapshot(warehouse).frames["comparison"]
    assert len(eligible_comparisons(frame)) == 4
    for column, value in (
        ("metric_version", "1.0.0"), ("comparison_eligibility", "unmatched_context"),
        ("availability_status", "provider_error"),
        ("llm_availability_status", "no_results"),
        ("language_code", None), ("serp_numerator", None),
    ):
        invalid = frame.copy()
        invalid[column] = value
        assert eligible_comparisons(invalid).empty


def test_duplicates_and_unavailable_not_absence(warehouse):
    frames = load_snapshot(warehouse).frames
    frames["serp"] = frames["serp"].loc[frames["serp"].index.repeat(3)]
    assert len(channel_rows(frames["serp"], "serp")) == 6
    frames["llm"]["availability_status"] = "provider_error"
    summary = presence_summary(frames)
    assert summary.loc[summary.channel.eq("LLM"), "presence_rate"].isna().all()
    assert not source_statuses(frames).empty


def test_no_data_and_missing_schema(tmp_path, warehouse):
    missing = tmp_path / "not-created.duckdb"
    assert load_snapshot(missing).message.startswith("Database not found")
    assert not missing.exists()
    empty = tmp_path / "empty.duckdb"
    with duckdb.connect(str(empty)):
        pass
    assert "schema" in load_snapshot(empty).message
    with duckdb.connect(str(empty)) as c:
        c.execute(MIGRATION_006)
    assert load_snapshot(empty).message.startswith("No completed releases")
    with duckdb.connect(str(warehouse)) as c:
        for table in (
            "release_serp_brand_visibility", "release_llm_brand_visibility",
            "release_comparison_brand_metrics",
        ):
            c.execute(f"DELETE FROM presentation.{table}")
    snapshot = load_snapshot(warehouse)
    assert snapshot.message is None
    assert presence_summary(snapshot.frames).empty
    assert source_statuses(snapshot.frames).empty
    assert locale_summary(snapshot.frames).empty
    with duckdb.connect(str(warehouse)) as c:
        c.execute("DROP TABLE presentation.release_serp_brand_visibility")
    assert "snapshot schema" in load_snapshot(warehouse).message


def test_streamlit_smoke_completed_and_filters(warehouse, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("GEO_DASHBOARD_DB", str(warehouse))
    app = AppTest.from_file(str(ROOT / "streamlit_app.py")).run(timeout=30)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "Overview", "Need × Market Map", "Brand Competition",
        "Evidence & Citation Explorer", "Opportunity Queue",
    ]
    assert any("Frozen release: done" in caption.value for caption in app.caption)
    app.sidebar.multiselect[0].set_value([]).run(timeout=30)
    assert not app.exception
    assert any("No channel evidence" in info.value for info in app.info)


def test_streamlit_smoke_missing_database(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("GEO_DASHBOARD_DB", str(tmp_path / "missing.duckdb"))
    app = AppTest.from_file(str(ROOT / "streamlit_app.py")).run(timeout=30)
    assert not app.exception
    assert "Database not found" in app.info[0].value