# ruff: noqa: E501
"""V2 channels, raw-grounded ranks and conservative semantic evidence."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment

from geo_research.storage.migrations import MIGRATION_009
from geo_research.transforms.feature_evidence import (
    TABLES,
    canonical_url,
    enrich_features,
    export_candidate_review,
    load_candidates,
    persist_features,
)
from tests.unit.test_response_evidence import context, payload, registry

ROOT = Path(__file__).resolve().parents[2]


def normalized(value, category="llm", reg=None, candidates=None, rules=None):
    result = enrich_features(context(category), value, reg or registry(), rules=rules, candidates=candidates)
    return result, {row["feature"]: row for row in result[TABLES[2]]}


def test_actual_bing_top_level_rank_paid_and_candidate():
    paths = list((ROOT / "data/raw/serp/dataforseo/bing/2026/09/28").rglob("f609c508-e696-4038-ab99-50f80750738d/response.json"))
    if not paths:
        pytest.skip("local raw not distributed")
    path = paths[0]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    raw = json.loads(path.read_text(encoding="utf-8"))
    result, features = normalized(raw, "serp", candidates=load_candidates(ROOT / "config/registries/brand_candidates.csv"))
    top = [row for row in result[TABLES[1]] if row["is_top_level"]]
    organic = [row for row in top if row["item_kind"] == "organic"]
    assert len(top) == 10 and len(organic) == 8
    assert len([row for row in top if row["item_kind"] == "paid"]) == 2
    assert (organic[0]["organic_rank"], organic[0]["page_position"]) == (1, 2)
    hoka = next(row for row in organic if "HOKA" in row["title"])
    assert (hoka["organic_rank"], hoka["page_position"], hoka["domain"]) == (6, 7, "www.jimmyselect.com")
    matches = [row for row in result[TABLES[5]] if row["item_id"] == hoka["item_id"]]
    assert any(row["identity_name"] == "HOKA" and row["review_status"] == "candidate" for row in matches)
    assert not any(row["evidence_type"] == "owned_organic" for row in matches)
    assert len([row for row in result[TABLES[1]] if row["parent_item_id"] == top[0]["item_id"] and row["item_kind"] == "ad_link"]) == 4
    assert features["organic"]["exhaustive_count"] == 8
    assert features["paid"]["exhaustive_count"] == 2
    info = result[TABLES[0]][0]
    assert (info["device"], info["os"], info["request_depth"]) == ("mobile", "ios", 10)
    assert info["provider_result_datetime"] and info["collected_at"]
    assert info["parse_success_rate"] == 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    for index, item in enumerate(top):
        assert json.loads(item["raw_evidence_json"]) == raw["retrieval"]["tasks"][0]["result"][0]["items"][index]


def test_citation_entities_occurrences_and_text_not_source_or_url():
    value = payload([{"type": "chat_gpt_text", "markdown": "Nike Nike [shop](https://nike.com/a#one) https://nike.com/Nike", "sources": [
        {"url": "https://NIKE.com/a#two", "snippet": "Nike Air source only"},
        {"url": "https://nike.com.evil.org/Nike"}, {"url": "https://nike.com@evil.org"}]}], sources=[{"url": "https://nike.com/a"}])
    result, features = normalized(value)
    answer = [row for row in result[TABLES[5]] if row["evidence_type"] == "answer_text"]
    assert len(answer) == 2 and {row["identity_id"] for row in answer} == {"nike"}
    assert len(result[TABLES[3]]) == 2
    assert len(result[TABLES[4]]) == 5
    assert len([row for row in result[TABLES[5]] if row["evidence_type"] == "owned_citation"]) == 1
    assert features["answer_text"]["coverage_status"] == "complete"
    assert features["citation"]["coverage_status"] == "partial"
    assert canonical_url("https://nike.com@evil.org") is None
    assert canonical_url("https://nike.com/a?q=1") != canonical_url("https://nike.com/a?q=2")
    source_only = payload([{"type": "gemini_text", "original_text": "generic answer https://nike.com/Nike", "sources": [{"url": "https://other.com", "snippet": "Nike"}]}])
    assert not normalized(source_only)[0][TABLES[5]]


def test_table_and_result_only_fallback_no_duplicate():
    value = payload([{"type": "chat_gpt_table", "table": [["Brand", "Use"], ["Nike", "running"]], "sources": []}])
    result, features = normalized(value)
    blocks = [row for row in result[TABLES[1]] if row["item_kind"] == "answer_text"]
    assert len(blocks) == 1 and blocks[0]["text_method"] == "scalar_table_cells"
    assert features["answer_text"]["exhaustive_count"] == 1
    value = payload([])
    value["retrieval"]["tasks"][0]["result"][0]["markdown"] = "Nike only result answer"
    result, features = normalized(value)
    assert features["answer_text"]["exhaustive_count"] == 1
    assert len([row for row in result[TABLES[5]] if row["evidence_type"] == "answer_text"]) == 1
    value["retrieval"]["tasks"][0]["result"][0]["items"] = None
    assert normalized(value)[1]["answer_text"]["exhaustive_count"] == 1
    unsupported = payload([{"type": "gemini_table", "table": {"unknown_cells": [{"brand": "Nike"}]}, "sources": []}])
    unsupported["retrieval"]["tasks"][0]["result"][0]["markdown"] = None
    result, features = normalized(unsupported)
    assert features["answer_text"]["coverage_status"] == "partial"
    assert json.loads(result[TABLES[1]][0]["raw_evidence_json"])["table"] == {"unknown_cells": [{"brand": "Nike"}]}


def test_unknowns_only_block_relevant_channels():
    value = payload([{"type": "organic", "url": "https://nike.com", "rank_group": 1, "rank_absolute": 2},
                     {"type": "paid", "url": "https://ad.com", "new_children": [{"title": "Nike"}]}])
    result, features = normalized(value, "serp")
    assert features["organic"]["exhaustive_count"] == 1
    assert features["paid"]["observed_count"] == 1 and features["paid"]["exhaustive_count"] is None
    assert result[TABLES[0]][0]["parse_success_rate"] == 0.5
    assert any(row["item_kind"] == "retained_nested" for row in result[TABLES[1]])
    value = payload([{"type": "gemini_text", "original_text": "Nike", "sources": None}])
    _, features = normalized(value)
    assert features["answer_text"]["exhaustive_count"] == 1
    assert features["citation"]["exhaustive_count"] is None


@pytest.mark.parametrize("status", ["pending", "provider_error", "missing", "quarantined"])
def test_unavailable_nulls(status):
    result = enrich_features(context("llm", status), None, registry())
    assert all(row["observed_count"] is None and row["exhaustive_count"] is None for row in result[TABLES[2]])
    assert not result[TABLES[1]]


def test_paid_not_owned_organic_and_alias_dedup_multilabel():
    reg = registry()
    reg["aliases"] = [{"brand_id": "nike", "alias_text": "NIKE"}, {"brand_id": "nike", "alias_text": "Nike"}]
    result, _ = normalized(payload([{"type": "paid", "title": "Nike", "url": "https://nike.com", "links": [{"type": "ad_link_element", "url": "https://nike.com"}]}]), "serp", reg)
    assert not any(row["evidence_type"] == "owned_organic" for row in result[TABLES[5]])
    assert len([row for row in result[TABLES[5]] if row["evidence_type"] == "paid_text"]) == 1
    assert len([row for row in result[TABLES[5]] if row["evidence_type"] == "paid_domain"]) == 2
    rules = [{"rule_id": key, "category_id": key, "category_name": key, "term": "shoes", "matched_field": "title", "item_kind": "product_card", "review_status": "approved", "taxonomy_version": "1", "rule_version": "1"} for key in ("running", "lifestyle")]
    result, _ = normalized(payload([{"type": "chat_gpt_products", "items": [{"title": "Nike shoes", "merchant": "Nike"}]}]), rules=rules)
    assert {row["identity_id"] for row in result[TABLES[5]] if row["identity_type"] == "category"} == {"running", "lifestyle"}


def test_actual_gemini_answer_not_blocked_by_null_sources():
    paths = list((ROOT / "data/raw/llm/dataforseo/gemini/2026/09/28").rglob("a1d7a15d-ada0-444b-ab9c-b24aee772624/response.json"))
    if not paths:
        pytest.skip("local raw not distributed")
    result, features = normalized(json.loads(paths[0].read_text(encoding="utf-8")))
    assert features["answer_text"]["observed_count"] > 0
    assert features["answer_text"]["exhaustive_count"] == features["answer_text"]["observed_count"]
    assert features["citation"]["coverage_status"] == "partial"
    assert len([row for row in result[TABLES[1]] if row["item_kind"] == "answer_text"]) == features["answer_text"]["observed_count"]


def test_persist_idempotent_candidate_review_and_multi_result(tmp_path):
    value = payload([{"type": "organic", "title": "HOKA", "rank_group": 1, "url": "https://publisher.com"}])
    value["retrieval"]["tasks"][0]["result"].append(copy.deepcopy(value["retrieval"]["tasks"][0]["result"][0]))
    result, _ = normalized(value, "serp", candidates=[{"candidate_id": "hoka", "candidate_name": "HOKA", "alias_text": "HOKA"}])
    assert len(result[TABLES[0]]) == 2
    assert len({row["item_id"] for row in result[TABLES[1]]}) == 2
    with duckdb.connect(":memory:") as con:
        con.execute("create schema silver")
        con.execute(MIGRATION_009)
        persist_features(con, result)
        persist_features(con, result)
        assert con.execute("select count(*) from silver.evidence_items_v2").fetchone()[0] == 2
        assert export_candidate_review(con, tmp_path / "review.csv") == 2
    assert "ownership_evidence" in (tmp_path / "review.csv").read_text(encoding="utf-8")
    value["retrieval"]["tasks"].append(copy.deepcopy(value["retrieval"]["tasks"][0]))
    assert normalized(value)[1]["answer_text"]["coverage_status"] == "unsupported"


def test_gold_v2_actual_occurrences_nulls_and_top10_gate():
    with duckdb.connect(":memory:") as con:
        con.execute("create schema silver; create schema analytics; create schema bronze")
        con.execute(MIGRATION_009)
        con.execute("create table bronze.brand_registry (brand_id varchar, canonical_name varchar, ownership_type varchar, active boolean, effective_start_date date, effective_end_date date)")
        con.execute("insert into bronze.brand_registry values ('nike','Nike','competitor',true,'2026-01-01',null)")
        result, _ = normalized(payload([{"type": "gemini_text", "markdown": "Nike Nike", "sources": [{"url": "https://nike.com/a"}, {"url": "https://nike.com/a"}]}], sources=[{"url": "https://nike.com/a"}]))
        persist_features(con, result)
        env = Environment()
        for model in ("silver_evidence_results_v2", "silver_readable_items_v2", "silver_feature_coverage_v2", "silver_feature_matches_v2", "gold_feature_brand_visibility_v2"):
            folder = "gold" if model.startswith("gold") else "silver"
            sql = env.from_string((ROOT / f"models/{folder}/{model}.sql").read_text(encoding="utf-8")).render(source=lambda schema, table: f"{schema}.{table}", ref=lambda name: f"analytics.{name}")
            con.execute(f"create view analytics.{model} as {sql}")
        assert con.execute("select exhaustive_brand_count from analytics.gold_feature_brand_visibility_v2 where feature='answer_text'").fetchone()[0] == 2
        assert con.execute("select exhaustive_brand_count from analytics.gold_feature_brand_visibility_v2 where feature='citation'").fetchone()[0] == 1
        assert con.execute("select observed_brand_count from analytics.gold_feature_brand_visibility_v2 where feature='organic'").fetchone()[0] is None
        value = payload([{"type": "organic", "url": f"https://other.com/{i}", "rank_group": i, "rank_absolute": i + 1} for i in range(1, 9)])
        persist_features(con, normalized(value, "serp")[0])
        assert con.execute("select owned_top3_presence, owned_top10_presence from analytics.gold_feature_brand_visibility_v2 where feature='organic'").fetchone() == (0, None)