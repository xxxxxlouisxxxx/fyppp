"""Experimental feature contracts; no inferred brands, approvals or market claims.

One result-brand-feature row. Presence denominators are complete result units,
not item counts or expanded comparison pairs. Partial positives are evidence,
never negative-capable samples. Citation shares use unique conservative URLs.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from geo_research.transforms.feature_evidence import TABLES
from geo_research.transforms.response_evidence import _id, _placeholder, _valid

VERSION = "research-metrics-1"
ATTRIBUTION = "exclusive-approved-identity-1"


def measure_features(
    evidence: dict[str, list[dict[str, Any]]], registry: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build counts/rates only for explicitly eligible registry identities.

    Unattributed and multi-brand slots remain in the full denominator, never
    silently renormalized. Count metrics have no share denominator. Output stays
    experimental until a separate reviewed benchmark and publication decision.
    """
    results = {row["result_id"]: row for row in evidence[TABLES[0]]}
    items = {row["item_id"]: row for row in evidence[TABLES[1]]}
    matches = [row for row in evidence[TABLES[5]]
               if row["identity_type"] == "brand"
               and row["review_status"] == "approved"]
    output = []
    for feature in evidence[TABLES[2]]:
        result = results[feature["result_id"]]
        if not result.get("collected_at"):
            # Unknown effective date cannot authorize an identity.
            continue
        as_of = date.fromisoformat(str(result["collected_at"])[:10])
        brands = {key: row for key, row in registry["brands"].items()
                  if _valid(row, as_of) and row.get("active") is True
                  and row.get("ownership_type") in {"owned", "competitor"}
                  and not _placeholder(row)
                  and row.get("review_status", "approved") == "approved"}
        channel = feature["feature"]
        coverage = feature["coverage_status"]
        complete = coverage == "complete"
        observed = coverage in {"complete", "partial"}
        method = {
            "answer_text": "answer_text", "organic": "owned_organic",
            "paid": "paid_domain", "product": "product_text",
            "citation": "owned_citation",
        }[channel]
        relevant = [row for row in matches
                    if row["result_id"] == result["result_id"]
                    and row["identity_id"] in brands
                    and row["evidence_type"] == method
                    and (channel != "paid" or items[row["item_id"]]["is_top_level"])]
        identities: dict[str, set[str]] = defaultdict(set)
        for match in relevant:
            identity = (match["citation_id"] if channel == "citation"
                        else match["item_id"])
            identities[identity].add(match["identity_id"])
        for brand_id, brand in brands.items():
            own = [row for row in relevant if row["identity_id"] == brand_id]
            if channel == "answer_text":
                count = len({(row["item_id"], row["matched_field"],
                              row["span_start"], row["span_end"]) for row in own})
                denominator = None  # occurrence count, not a share
            else:
                count = sum(value == {brand_id} for value in identities.values())
                denominator = feature["exhaustive_count"] if complete else None
            any_positive = bool(own)
            presence = int(any_positive) if complete or any_positive else None
            count = count if observed else None
            if not observed:
                presence = None
            output.append({
                **{key: result.get(key) for key in (
                    "observation_id", "result_id", "source_category", "query_id",
                    "provider", "engine_or_platform", "language_code",
                    "location_code", "collected_at", "request_id", "response_id",
                    "raw_file_hash", "collection_status", "collection_window",
                )},
                "metric_id": _id(result["result_id"], brand_id, channel, VERSION),
                "brand_id": brand_id, "brand": brand["canonical_name"],
                "feature": channel, "coverage_status": coverage,
                "presence": presence,
                "presence_numerator": presence if complete else None,
                "presence_denominator": 1 if complete else None,
                "observed_brand_count": count,
                "exhaustive_brand_count": count if complete else None,
                "share_numerator": (
                    count if complete and channel != "answer_text" else None
                ),
                "share_denominator": denominator,
                "share": count / denominator if complete and denominator else None,
                "ambiguous_entities": sum(
                    len(value) > 1 for value in identities.values()
                ),
                "metric_version": VERSION, "attribution_version": ATTRIBUTION,
                "parser_version": result["enrichment_version"],
                "registry_version": registry["version"],
                "quality_status": "experimental",
                "sample_unit": "result-brand-feature",
                "limitations": "Observed samples; no market/causal/ROI interpretation",
            })
    return output