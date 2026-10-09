"""Evidence-first name proposals, not entity approval or owned-domain inference."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any


def discover_explicit_brands(items: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Propose names from explicit product `brand` fields in normalized evidence.

    Unknown titles/answer text cannot reliably identify arbitrary brand names with
    a regex. Those require manual annotation or a separately validated entity
    extractor. No dictionary restriction, registry writes, domain attribution,
    aliases, product-model merging or commercial conclusions are performed.
    """
    proposals = []
    for item in items:
        if item.get("item_kind") != "product":
            continue
        required = ("observation_id", "result_id", "item_id", "json_path")
        if any(not isinstance(item.get(key), str) or not item[key] for key in required):
            raise ValueError("candidate discovery requires original evidence lineage")
        try:
            raw = json.loads(item["raw_evidence_json"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "candidate discovery requires retained raw item JSON"
            ) from error
        name = raw.get("brand") if isinstance(raw, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        candidate_id = "candidate-" + hashlib.sha256(
            name.casefold().encode("utf-8")
        ).hexdigest()[:24]
        proposals.append({
            "candidate_id": candidate_id, "candidate_name": name,
            "review_status": "candidate", "method": "explicit_product_brand_field_v1",
            **{key: item[key] for key in required},
            "matched_field": "brand", "matched_text": raw["brand"],
            "limitations": "Provider label; identity/alias/ownership unverified",
        })
    # Each occurrence retains its original lineage; names are not KPI sample units.
    return proposals