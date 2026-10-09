"""Verified DataForSEO Yahoo Organic Standard task-post contract."""

from __future__ import annotations

from typing import Any

from geo_research.adapters.serp.base import SERPAdapter
from geo_research.connectors.dataforseo.capabilities import CapabilityEvidence
from geo_research.domain.serp import Query, SearchTarget


class YahooOrganicAdapter(SERPAdapter):
    capability = CapabilityEvidence(
        capability_key="serp.yahoo.organic",
        capability_state="verified",
        evidence_version="2026-09-27",
        endpoint="https://api.dataforseo.com/v3/serp/yahoo/organic/task_post",
        http_method="POST",
        required_fields=("keyword", "location_code", "language_code"),
        fixture_available=True,
    )
    search_engine = "yahoo"

    def _build_verified_payload(
        self, query: Query, target: SearchTarget
    ) -> list[dict[str, Any]]:
        if target.retrieval_method != "standard":
            raise ValueError(
                "Yahoo Organic task_post requires retrieval_method=standard"
            )
        if not target.location_code.isdecimal():
            raise ValueError(
                "Yahoo Organic task_post requires a numeric location_code"
            )
        return [
            {
                "keyword": query.keyword,
                "location_code": int(target.location_code),
                "language_code": target.language_code,
                "device": target.device,
                "depth": target.depth,
            }
        ]
