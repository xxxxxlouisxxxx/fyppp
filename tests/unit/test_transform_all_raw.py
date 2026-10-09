# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.raw_store import RawEvidence, RawStore

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("transform_all_raw", ROOT / "scripts/transform_all_raw.py")
assert spec and spec.loader
bulk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bulk)


def test_new_bulk_run_persists_response_evidence_without_approving_brands(tmp_path):
    raw = tmp_path / "data/raw"
    evidence(raw, category="llm", engine="gemini")
    summary = bulk.run(tmp_path, raw_date=date(2026, 9, 28))
    assert summary["raw_unchanged"]
    assert summary["response_evidence_observations"] == 1
    with duckdb.connect(summary["database"], read_only=True) as connection:
        row = connection.execute("SELECT query_text, top_level_item_count, answer_block_count, distinct_brand_count, brand_coverage_status FROM silver.silver_response_summaries").fetchone()
        assert row == ("real keyword", 1, 1, None, "no_approved_registry")
        assert connection.execute("SELECT count(*) FROM silver.silver_response_items").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM silver.silver_item_brand_evidence").fetchone()[0] == 0


def test_finalize_rejects_failed_dbt_without_touching_summary(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text('{"database":"not-opened.duckdb"}', encoding="utf-8")
    target = tmp_path / "dbt_target"
    target.mkdir()
    (target / "run_results.json").write_text(
        '{"results":[{"status":"fail"}]}', encoding="utf-8"
    )
    before = summary.read_bytes()
    with pytest.raises(ValueError, match="dbt failed"):
        bulk.finalize_dbt_export(tmp_path)
    assert summary.read_bytes() == before


def test_date_scope_uses_exact_raw_folder_date(tmp_path):
    root = tmp_path / "raw"
    for folder_date in ("2026/09/28", "2026/09/27", "2025/09/28"):
        for category in ("serp", "llm"):
            folder = root / category / "dataforseo" / "google" / folder_date / "run" / "request"
            folder.mkdir(parents=True)
            (folder / "response.json").write_text("{}", encoding="utf-8")
    rows = bulk.audit_raw(root, date(2026, 9, 28))
    assert len(rows) == 2
    assert {row["category"] for row in rows} == {"serp", "llm"}
    assert all("/2026/09/28/" in row["path"].replace("\\", "/") for row in rows)
    assert len(bulk.audit_raw(root)) == 6


def evidence(root: Path, category="serp", engine="google", request_id="request-1", status=20000, family="retrieval"):
    item = {"type": "organic", "rank_group": 1, "rank_absolute": 2,
            "domain": "baike.baidu.com", "url": "https://baike.baidu.com/item/ENJOYZ/18604110",
            "title": "ENJOYZ 足球装备", "description": None}
    if category == "llm":
        item = {"type": "chat_gpt_text", "original_text": "actual answer", "sources": []}
    task = {"id": "provider-task-1", "status_code": status,
            "data": {"se": engine, "keyword": "real keyword", "location_code": 2156,
                     "language_code": "zh_CN", "device": "Mobile", "se_type": "organic"},
            "result": [{"items": [item]}] if status == 20000 else None}
    block = {"status_code": 20000, "tasks": [task]}
    payload = block if family == "direct" else {family: block}
    return RawStore(root).write(RawEvidence(source_category=category, provider="dataforseo",
        platform_or_engine=engine, run_id="real-run", request_id=request_id,
        collected_at=datetime(2026, 9, 28, 4, 5, tzinfo=UTC),
        request_payload={"post": [{"keyword": "real keyword"}]}, response_payload=payload))


def test_audit_invalid_json_missing_triple_checksum_and_count_reconciliation(tmp_path):
    root = tmp_path / "raw"
    good = evidence(root)
    (good.directory / "response.pretty.json").write_text(good.response.path.read_text(encoding="utf-8"), encoding="utf-8")
    bad = evidence(root, request_id="bad-json")
    bad.response.path.write_text("{bad", encoding="utf-8")
    orphan = root / "llm/orphan"
    orphan.mkdir(parents=True)
    (orphan / "response.json").write_text("{}", encoding="utf-8")
    rows = bulk.audit_raw(root)
    assert len(rows) == 8
    assert sum(not row["json_valid"] for row in rows) == 1
    assert sum(row["role"] == "response" for row in rows) == 3
    assert next(row for row in rows if row["path"].endswith("response.pretty.json"))["disposition"] == "duplicate_response_representation"
    bad_row = next(row for row in rows if row["request_id"] == "bad-json" and row["role"] == "response")
    assert not bad_row["triple_valid"]
    assert "checksum mismatch for response.json" in bad_row["integrity_problems"]
    assert "missing metadata.json" in next(row for row in rows if "orphan" in row["path"])["integrity_problems"]


def test_context_requires_request_id_and_hash_and_conflicts_not_guessed():
    meta = {"request_id": "r"}
    index = {("r", "sha"): [{"query_id": "q", "collection_window": "window", "provenance_database": "a"}]}
    assert bulk.reconcile_context(meta, "wrong", index) == ({}, [], [])
    context, sources, conflicts = bulk.reconcile_context(meta, "sha", index)
    assert context == {"query_id": "q", "collection_window": "window"}
    assert sources == ["a"] and not conflicts
    index[("r", "sha")].append({"query_id": "different", "provenance_database": "b"})
    context, _, conflicts = bulk.reconcile_context(meta, "sha", index)
    assert "query_id" not in context and conflicts == ["query_id"]


@pytest.mark.parametrize("category,engine,family,status,outcome", [
    ("serp", "google", "post", 20100, "pending"),
    ("serp", "bing", "retrieval", 40601, "provider_error"),
    ("serp", "yahoo", "direct", 20000, "available"),
    ("serp", "baidu", "retrieval", 20000, "available"),
    ("llm", "chat_gpt", "live_advanced", 20000, "available"),
    ("llm", "gemini", "post", 20100, "pending"),
    ("llm", "gemini", "direct", 40601, "provider_error"),
])
def test_local_transform_status_idempotence_and_true_settings(tmp_path, category, engine, family, status, outcome):
    root = tmp_path / "raw"
    result = evidence(root, category, engine, status=status, family=family)
    before = result.response.path.read_bytes()
    rows = bulk.audit_raw(root)
    row = next(row for row in rows if row["role"] == "response")
    database_path = tmp_path / "new.duckdb"
    DuckDBStore(database_path).initialize()
    with duckdb.connect(str(database_path)) as connection:
        database = bulk._LocalDatabase(connection)
        report = bulk.transform_response(database, root, row, {"query_id": "authoritative", "collection_window": "approved-window"})
        assert report["status"] == outcome
        assert bulk.transform_response(database, root, row, {})["status"] == "idempotent"
        assert connection.execute("select count(*) from bronze.api_requests").fetchone()[0] == 1
        assert connection.execute("select query_id, collection_window from bronze.api_requests").fetchone() == ("authoritative", "approved-window")
        table = "silver.silver_search_observations" if category == "serp" else "silver.silver_llm_observations"
        assert connection.execute(f"select outcome_status from {table}").fetchone()[0] == outcome
        if category == "serp":
            assert connection.execute(f"select location_code,language_code,device from {table}").fetchone() == ("2156", "zh_CN", "Mobile")
            assert connection.execute("select count(*) from silver.silver_organic_results").fetchone()[0] == int(status == 20000)
        elif status != 20000:
            assert connection.execute(f"select response_text,items_count from {table}").fetchone() == (None, 0)
    assert result.response.path.read_bytes() == before


def test_same_authoritative_window_does_not_collapse_serp_observations(tmp_path):
    root = tmp_path / "raw"
    evidence(root, request_id="one")
    evidence(root, request_id="two")
    path = tmp_path / "new.duckdb"
    DuckDBStore(path).initialize()
    with duckdb.connect(str(path)) as connection:
        database = bulk._LocalDatabase(connection)
        for row in bulk.audit_raw(root):
            if row["role"] == "response":
                bulk.transform_response(database, root, row, {"query_id": "same-query", "collection_window": "true-window"})
        assert connection.execute("select count(*),count(distinct observation_id) from silver.silver_search_observations").fetchone() == (2, 2)
        assert connection.execute("select count(distinct collection_window),count(distinct query_id) from silver.silver_search_observations").fetchone() == (1, 1)


def test_full_run_counts_empty_presentation_and_no_fixture_seed(tmp_path):
    root = tmp_path / "data/raw"
    evidence(root, engine="baidu")
    evidence(root, category="llm", engine="gemini", request_id="pending", status=20100, family="post")
    summary = bulk.run(tmp_path)
    assert summary["json_files"] == 6 and summary["supported_responses"] == 2
    assert summary["raw_unchanged"] and summary["all_files_accounted"] and summary["response_reconciliation"]
    assert summary["statuses"] == {"available": 1, "pending": 1}
    assert Path(summary["export"], "manifest.csv").exists()
    with duckdb.connect(summary["database"], read_only=True) as connection:
        assert connection.execute("select count(*) from presentation.releases").fetchone()[0] == 0
        assert connection.execute("select count(*) from bronze.comparison_registry").fetchone()[0] == 0
        assert connection.execute("select count(*) from bronze.brand_registry").fetchone()[0] == 0
        assert connection.execute("select count(*) from bronze.api_requests where query_id is null").fetchone()[0] == 2
        assert connection.execute("select collection_window from bronze.api_requests order by request_id").fetchall() == [("raw-request:pending",), ("raw-request:request-1",)]


def test_known_envelope_deep_copy_and_no_answer_for_unknown_contract():
    payload = {"live_advanced": {"tasks": [{"status_code": 20000, "result": [{"items": []}]}]}}
    before = json.dumps(payload)
    _, block = bulk.envelope(payload)
    block["tasks"][0]["result"][0]["items"].append("changed")
    assert json.dumps(payload) == before
    with pytest.raises(ValueError, match="unsupported envelope"):
        bulk.envelope({"answer": "not a verified contract"})


def test_read_only_provenance_exact_sha_and_null_context_not_overridden(tmp_path):
    root = tmp_path / "raw"
    evidence(root)
    row = next(row for row in bulk.audit_raw(root) if row["role"] == "response")
    source = tmp_path / "authoritative.duckdb"
    DuckDBStore(source).initialize()
    with duckdb.connect(str(source)) as connection:
        bulk.transform_response(bulk._LocalDatabase(connection), root, row,
                                {"query_id": "approved", "collection_window": "actual"})
    before = source.read_bytes()
    index, _, reports = bulk.read_provenance([source])
    metadata = json.loads((root / row["path"]).with_name("metadata.json").read_text(encoding="utf-8"))
    context, paths, conflicts = bulk.reconcile_context(metadata, row["sha256"], index)
    assert context["query_id"] == "approved" and context["collection_window"] == "actual"
    assert not conflicts and paths == [str(source)]
    assert reports[0]["read_only"] and reports[0]["error"] is None
    assert source.read_bytes() == before


def test_full_run_quarantines_invalid_triple_without_registering(tmp_path):
    root = tmp_path / "data/raw"
    result = evidence(root)
    result.response.path.write_text("{}", encoding="utf-8")
    summary = bulk.run(tmp_path)
    assert summary["response_files"] == 1 and summary["quarantined_responses"] == 1
    assert summary["supported_responses"] == 0 and summary["response_reconciliation"]
    with duckdb.connect(summary["database"], read_only=True) as connection:
        assert connection.execute("select count(*) from bronze.api_requests").fetchone()[0] == 0