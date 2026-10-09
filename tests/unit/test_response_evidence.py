# ruff: noqa: E501
"""Raw-grounded composition and conservative identity/category regressions."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

from geo_research.storage.migrations import MIGRATION_008
from geo_research.transforms.llm_raw import transform_llm_raw_payload
from geo_research.transforms.response_evidence import (
    TABLES,
    enrich_response,
    hostname,
    load_brand_registry,
    load_category_rules,
    persist_evidence,
    spans,
)

ROOT = Path(__file__).resolve().parents[2]


def context(category="llm", status="available"):
    return {"observation_id": "obs", "request_id": "req", "response_id": "resp",
            "raw_file_hash": "hash", "source_category": category,
            "collection_status": status, "collected_at": datetime(2026, 9, 28, tzinfo=UTC),
            "provider": "dataforseo", "engine_or_platform": "chat_gpt"}


def registry():
    return {"brands": {"nike": {"brand_id": "nike", "canonical_name": "Nike"},
                       "air": {"brand_id": "air", "canonical_name": "Nike Air"}},
            "aliases": [], "domains": [{"brand_id": "nike", "domain": "nike.com"}],
            "version": "reviewed-test-registry"}


def payload(items, sources=None):
    return {"retrieval": {"status_code": 20000, "tasks": [{"status_code": 20000,
        "data": {"keyword": "running shoes", "language_code": "zh_CN", "location_code": 2156},
        "result": [{"items": items, "items_count": len(items), "sources": sources or [],
                    "markdown": "DUPLICATE Nike Air answer"}]}]}}


def summarize(value, category="llm", reg=None, rules=None, status="available"):
    result = enrich_response(context(category, status), value, reg or registry(), rules)
    return result, result[TABLES[0]][0]


def test_alias_boundaries_longest_and_casefold_offsets():
    assert spans("NIKE Air Nikes Nike", [("nike", "Nike"), ("air", "Nike Air")]) == [
        ("air", 0, 8, "Nike Air"), ("nike", 15, 19, "Nike")]
    assert spans("安踏体育安踏", [("short", "安踏"), ("long", "安踏体育")]) == [
        ("long", 0, 4, "安踏体育"), ("short", 4, 6, "安踏")]
    assert spans("Straße", [("x", "STRASSE")])[0][1:3] == (0, 6)
    assert len(spans("Nike", [("a", "Nike"), ("b", "Nike")])) == 2


def test_channel_separation_merchants_spoofs_and_no_markdown_duplicate():
    value = payload([
        {"type": "chat_gpt_text", "markdown": "Nike Air shoes", "sources": [
            {"url": "https://publisher.com", "snippet": "Nike only in source"},
            {"url": "https://www.nike.com/path"},
            {"url": "https://nike.com.evil.org"},
            {"url": "https://nike.com@evil.org"}]},
        {"type": "chat_gpt_products", "items": [
            {"title": "generic shoes", "merchants": "Nike", "domain": "nike.com"},
            {"title": "Nike running shoes"}]},
        {"type": "chat_gpt_table", "markdown": "|Nike|[shop](https://nike.com/table)|"},
    ], sources=[{"url": "https://nike.com/result"}])
    result, summary = summarize(value)
    assert summary["evidence_coverage_status"] == "complete"
    assert (summary["top_level_item_count"], summary["product_card_count"], summary["answer_block_count"]) == (3, 2, 2)
    matches = result[TABLES[2]]
    assert len([r for r in matches if r["evidence_type"] == "answer_text"]) == 2
    assert len([r for r in matches if r["evidence_type"] == "citation"]) == 3
    assert len([r for r in matches if r["evidence_type"] == "product_card"]) == 1
    assert summary["answer_brand_ids"] == ["air", "nike"]
    assert summary["cited_brand_ids"] == ["nike"]
    assert hostname("https://nike.com@evil.org") is None
    flat = transform_llm_raw_payload(value)
    assert flat["items"][1]["raw_item"]["items"] == value["retrieval"]["tasks"][0]["result"][0]["items"][1]["items"]
    assert flat["items"][0]["result_sources"] == [{"url": "https://nike.com/result"}]
    source_only, source_summary = summarize(payload([
        {"type": "chat_gpt_text", "markdown": "generic answer", "sources": [
            {"url": "https://publisher.com", "snippet": "Nike"}]}]))
    assert source_summary["distinct_brand_count"] == 0 and not source_only[TABLES[2]]


def test_reviewed_multilabel_categories_and_raw_category_mapping(tmp_path):
    path = tmp_path / "rules.csv"
    path.write_text("rule_id,category_id,category_name,term,matched_field,item_kind,taxonomy_version,rule_version,review_status,active\n"
                    "r1,running,Running shoes,running,title,product_card,2026-1,1,approved,true\n"
                    "r2,lifestyle,Lifestyle shoes,shoes,title,product_card,2026-1,1,approved,true\n"
                    "r3,sports,Sports footwear,Athletic,category,product_card,2026-1,2,approved,true\n"
                    "r4,fake,Unreviewed,Nike,title,product_card,2026-1,1,pending,true\n", encoding="utf-8")
    rules = load_category_rules(path)
    result, summary = summarize(payload([{"type": "chat_gpt_products", "items": [
        {"title": "Nike running shoes", "category": "Athletic"}]}]), rules=rules)
    assert summary["business_categories"] == ["lifestyle", "running", "sports"]
    assert len(result[TABLES[3]]) == 3
    assert {r["method"] for r in result[TABLES[3]]} == {"reviewed_explicit_term", "reviewed_raw_category_map"}
    assert summarize(payload([]))[1]["business_categories"] == ["unknown"]


@pytest.mark.parametrize("status", ["pending", "provider_error", "missing", "quarantined"])
def test_unavailable_never_semantic_zero(status):
    _, summary = summarize(None, status=status)
    assert summary["evidence_coverage_status"] == status
    assert all(summary[key] is None for key in ("distinct_brand_count", "organic_count", "product_card_count", "answer_block_count"))


def test_partial_missing_items_unknown_nested_and_multiple_results():
    value = payload([{"type": "chat_gpt_text", "markdown": "Nike", "new_children": [{"title": "Nike"}]}])
    result, summary = summarize(value)
    assert summary["evidence_coverage_status"] == "partial"
    assert summary["top_level_item_count"] == 1
    assert summary["distinct_brand_count"] is None
    assert result[TABLES[1]][0]["coverage_status"] == "partial"
    for item in [{"type": "unknown"}, {"type": "chat_gpt_products"}, {"type": "chat_gpt_text", "markdown": None}]:
        assert summarize(payload([item]))[1]["evidence_coverage_status"] == "partial"
    broken = payload([])
    broken["retrieval"]["tasks"][0]["result"][0]["items"] = None
    assert summarize(broken)[1]["top_level_item_count"] is None
    value = payload([])
    value["retrieval"]["tasks"][0]["result"].append({"items": [{"type": "organic", "title": "Nike"}]})
    with pytest.raises(ValueError, match="multiple LLM results"):
        transform_llm_raw_payload(value)
    assert summarize(value)[1]["evidence_coverage_status"] == "unsupported"
    assert summarize(value, "serp")[1]["top_level_item_count"] == 1
    value["retrieval"]["tasks"].append(copy.deepcopy(value["retrieval"]["tasks"][0]))
    assert summarize(value, "serp")[1]["evidence_coverage_status"] == "unsupported"


def test_raw_provider_status_takes_precedence():
    value = payload([])
    for code, expected in [(20100, "pending"), (40100, "provider_error")]:
        value["retrieval"]["tasks"][0]["status_code"] = code
        assert summarize(value)[1]["evidence_coverage_status"] == expected
        _, summary = summarize(value, "serp", status=expected)
        assert summary["query_text"] == "running shoes"
        assert summary["status_code"] == code
        assert summary["organic_count"] is None


def test_actual_baidu_11_7_20_9_read_only():
    path = ROOT / "data/raw/serp/dataforseo/baidu/2026/09/28/serp-direct-retrieval-0a8f4bf0-1045-4991-917f-031cc1bebe37/eed6842c-ba19-4977-aecc-867ddbb63635/response.json"
    if not path.exists():
        pytest.skip("local raw evidence not distributed with repository")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result, summary = summarize(json.loads(path.read_text(encoding="utf-8")), "serp")
    assert summary["evidence_coverage_status"] == "complete", summary["issues_json"]
    assert (summary["top_level_item_count"], summary["organic_count"], summary["product_card_count"], summary["image_count"]) == (11, 7, 20, 9)
    assert len([r for r in result[TABLES[1]] if r["item_kind"] == "related_module"]) == 2
    assert all(r["parent_item_id"] for r in result[TABLES[1]] if r["item_kind"] in {"product_card", "image", "related_search"})
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_actual_llm_nested_payload_is_retained():
    path = ROOT / "data/raw/llm/dataforseo/chat_gpt/2026/09/28/llm-retrieval-42aee327-174a-42ba-be9b-3760ccafc8f3/32c2b771-9252-41b8-994b-ff3c75657ab3/response.json"
    if not path.exists():
        pytest.skip("local raw evidence not distributed with repository")
    value = json.loads(path.read_text(encoding="utf-8"))
    flat = transform_llm_raw_payload(value)
    result, summary = summarize(value)
    assert {"chat_gpt_text", "chat_gpt_table", "chat_gpt_products"} <= set(summary["result_types"])
    expected = sum(len(i["raw_item"].get("items") or []) for i in flat["items"] if i["item_type"] == "chat_gpt_products")
    assert len([r for r in result[TABLES[1]] if r["item_kind"] == "product_card"]) == expected > 0
    assert any(r["item_kind"] == "citation" for r in result[TABLES[1]])


def test_registry_missing_unapproved_inactive_and_empty():
    with duckdb.connect(":memory:") as connection:
        assert not load_brand_registry(connection)["brands"]
        connection.execute("CREATE SCHEMA bronze")
        connection.execute("CREATE TABLE bronze.brand_registry (brand_id VARCHAR, canonical_name VARCHAR, ownership_type VARCHAR, active BOOLEAN)")
        connection.execute("INSERT INTO bronze.brand_registry VALUES ('a','Nike','TO_BE_VERIFIED',true),('b','Other','owned',false),('c','Example','owned',true),('d','Good','arbitrary',true),('ok','Nike','competitor',true)")
        reg = load_brand_registry(connection)
        assert set(reg["brands"]) == {"ok"}
        reg["brands"] = {}
        _, summary = summarize(payload([]), reg=reg)
        assert summary["distinct_brand_count"] is None
        assert summary["brand_coverage_status"] == "no_approved_registry"
        assert summary["answer_block_count"] == 0


def test_persist_atomic_idempotent_and_dbt_wrappers():
    with duckdb.connect(":memory:") as connection:
        connection.execute(MIGRATION_008)
        result, _ = summarize(payload([{"type": "chat_gpt_text", "markdown": "Nike"}]))
        for _ in range(2):
            connection.execute("BEGIN")
            persist_evidence(connection, result)
            connection.execute("COMMIT")
        env = Environment()
        for table in TABLES:
            sql = env.from_string((ROOT / f"models/silver/{table}.sql").read_text()).render(source=lambda schema, name: f"{schema}.{name}")
            assert len(connection.execute(sql).fetchall()) == len(result[table])
        assert connection.execute("SELECT count(*) FROM silver.silver_response_summaries").fetchone()[0] == 1
        replacement, _ = summarize(payload([]))
        connection.execute("BEGIN")
        persist_evidence(connection, replacement)
        connection.execute("ROLLBACK")
        assert connection.execute("SELECT count(*) FROM silver.silver_item_brand_evidence").fetchone()[0] == 1


def test_legacy_gold_excludes_additive_raw_fields():
    value = payload([{"type": "chat_gpt_products", "items": [{"title": "Nike"}]}], sources=[{"snippet": "Nike"}])
    flat = transform_llm_raw_payload(value)
    with duckdb.connect(":memory:") as connection:
        legacy = connection.execute("SELECT json_group_array(json_merge_patch(value, '{\"raw_item\":null,\"result_sources\":null,\"json_path\":null}')) FROM json_each(?)", [json.dumps(flat["items"])]).fetchone()[0]
    assert "Nike" not in legacy
    sql = (ROOT / "models/gold/gold_llm_brand_visibility.sql").read_text()
    assert "json_merge_patch" in sql