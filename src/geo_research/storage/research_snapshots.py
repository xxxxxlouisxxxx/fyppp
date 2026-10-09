"""Atomic additive research snapshots, isolated from historical metric semantics.

Only explicitly requested by a publisher. Always experimental; eligible registry
identities are not benchmark validation. No raw text is copied into these rows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import duckdb

from geo_research.domain.comparisons import Comparison
from geo_research.transforms.feature_evidence import TABLES
from geo_research.transforms.research_metrics import measure_features
from geo_research.transforms.response_evidence import (
    _id,
    _rows,
    load_brand_registry,
)

KINDS = ("metrics", "coverage", "candidates", "mappings", "needs", "pairs")
SCHEMA = """
CREATE TABLE IF NOT EXISTS presentation.release_research_rows (
    release_id VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    row_id VARCHAR NOT NULL,
    payload_json VARCHAR NOT NULL,
    PRIMARY KEY (release_id, kind, row_id)
);
"""


def publish_research(
    connection: duckdb.DuckDBPyConnection, release_id: str,
    comparisons: tuple[Comparison, ...],
) -> None:
    """Freeze source rows in the caller's release transaction; fail closed.

    All feature observations must exist in this release's channel snapshots with
    identical response hash. Mapping approvals are supplied explicitly, not read
    from current CSV on dashboard access. Need labels only come from approved
    explicit category rules; missing taxonomy remains unavailable.
    """
    evidence = {table: _rows(connection, f"SELECT * FROM silver.{table}")
                for table in TABLES}
    source: list[tuple[Any, ...]] = []
    for table, instrument, category, source_column in (
        ("release_serp_brand_visibility", "query_id", "serp", "search_engine"),
        ("release_llm_brand_visibility", "prompt_id", "llm", "platform"),
    ):
        result = connection.execute(
            f"SELECT DISTINCT observation_id, raw_file_hash, collection_window, "
            f"{instrument}, response_id, provider, {source_column}, "
            f"language_code, location_code FROM presentation.{table} "
            "WHERE release_id=?",
            [release_id],
        ).fetchall()
        source.extend((category, *row) for row in result)
    by_observation: dict[str, set[tuple[Any, ...]]] = {}
    for category, observation, *context in source:
        by_observation.setdefault(observation, set()).add(
            (category, *context)
        )
    results = {}
    for result in evidence[TABLES[0]]:
        context = by_observation.get(result["observation_id"], set())
        if len(context) != 1:
            raise ValueError("research observation has missing/ambiguous context")
        (category, raw_hash, window, instrument, response_id, provider,
         engine, language, location) = next(iter(context))
        if not raw_hash or result["raw_file_hash"] != raw_hash:
            raise ValueError("research response hash differs from frozen release")
        if result.get("query_id") != instrument:
            raise ValueError("research instrument differs from frozen release")
        expected = {
            "source_category": category, "response_id": response_id,
            "provider": provider, "engine_or_platform": engine,
            "language_code": language, "location_code": location,
        }
        for key, value in expected.items():
            if result.get(key) != value:
                raise ValueError(f"research {key} differs from frozen release")
        result["collection_window"] = window
        results[result["result_id"]] = result
    for table in TABLES[1:]:
        if any(row["result_id"] not in results for row in evidence[table]):
            raise ValueError("orphan research evidence")
    rows: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
    rows["metrics"] = measure_features(evidence, load_brand_registry(connection))
    for feature in evidence[TABLES[2]]:
        result = results[feature["result_id"]]
        safe_context = {
            key: result.get(key) for key in (
                "result_id", "observation_id", "source_category", "query_id",
                "provider", "engine_or_platform", "language_code", "location_code",
                "collection_window", "collection_status", "raw_file_hash",
                "response_id", "request_id", "collected_at", "enrichment_version",
            )
        }
        rows["coverage"].append({
            **safe_context, **feature, "quality_status": "experimental",
        })
    for match in evidence[TABLES[5]]:
        if match["review_status"] == "candidate":
            # Name and lineage only, no unapproved original source snippet.
            rows["candidates"].append({
                key: match[key] for key in (
                    "evidence_id", "observation_id", "result_id", "item_id",
                    "identity_id", "identity_name", "identity_type", "method",
                    "review_status", "registry_version", "enrichment_version",
                )
            })
        if (
            match["identity_type"] == "category"
            and match["review_status"] == "approved"
        ):
            rows["needs"].append({
                "result_id": match["result_id"], "need_id": match["identity_id"],
                "need": match["identity_name"], "mapping_method": match["method"],
                "registry_version": match["registry_version"],
                "quality_status": "experimental",
            })
    pairs_seen: set[tuple[str, str]] = set()
    for mapping in comparisons:
        pair = (mapping.query_id, mapping.prompt_id)
        if mapping.active and pair in pairs_seen:
            raise ValueError("duplicate active research comparison")
        build_date = datetime.now(UTC).date()
        if (not mapping.active or mapping.effective_start_date > build_date
                or (mapping.effective_end_date
                    and mapping.effective_end_date < build_date)):
            continue
        pairs_seen.add(pair)
        rows["mappings"].append(mapping.model_dump(mode="json"))
        serp = [row for row in results.values()
                if row["source_category"] == "serp"
                and row["query_id"] == mapping.query_id]
        llm = [row for row in results.values()
               if row["source_category"] == "llm"
               and row["query_id"] == mapping.prompt_id]
        for left in serp:
            for right in llm:
                keys = ("language_code", "location_code", "collection_window")
                if not all(left.get(key) and left[key] == right.get(key)
                           for key in keys):
                    continue
                rows["pairs"].append({
                    "comparison_id": mapping.comparison_id,
                    "serp_result_id": left["result_id"],
                    "llm_result_id": right["result_id"],
                    "serp_observation_id": left["observation_id"],
                    "llm_observation_id": right["observation_id"],
                    **{key: left[key] for key in keys},
                    "mapping_version": mapping.mapping_version,
                    "quality_status": "experimental",
                    "limitations": "Matched instrument context; pairs are dependent",
                })
    connection.execute(SCHEMA)
    for kind, records in rows.items():
        # Exact duplicate rule/alias evidence is not a new sample.
        unique = {json.dumps(row, sort_keys=True, default=str): row for row in records}
        for payload in unique:
            connection.execute(
                "INSERT INTO presentation.release_research_rows VALUES (?, ?, ?, ?)",
                [release_id, kind, _id(kind, payload), payload],
            )