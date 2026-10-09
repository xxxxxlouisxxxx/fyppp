"""Verified DataForSEO Bing Organic Standard task-post contract."""

from __future__ import annotations

from typing import Any

from geo_research.adapters.serp.base import SERPAdapter
from geo_research.connectors.dataforseo.capabilities import CapabilityEvidence
from geo_research.domain.serp import Query, SearchTarget


class BingOrganicAdapter(SERPAdapter):
    capability = CapabilityEvidence(
        capability_key="serp.bing.organic",
        capability_state="verified",
        evidence_version="2026-09-27",
        endpoint="https://api.dataforseo.com/v3/serp/bing/organic/task_post",
        http_method="POST",
        required_fields=("keyword", "location_code", "language_code"),
        fixture_available=True,
    )
    search_engine = "bing"

    def _build_verified_payload(
        self, query: Query, target: SearchTarget
    ) -> list[dict[str, Any]]:
        if target.retrieval_method != "standard":
            raise ValueError(
                "Bing Organic task_post requires retrieval_method=standard"
            )
        if not target.location_code.isdecimal():
            raise ValueError(
                "Bing Organic task_post requires a numeric location_code"
            )
        device = target.device.casefold()
        operating_system = target.operating_system.casefold()
        if device == "mobile":
            operating_system = {
                "windows": "android",
                "macos": "ios",
            }.get(operating_system, operating_system)
        return [
            {
                "keyword": query.keyword,
                "location_code": int(target.location_code),
                "language_code": target.language_code,
                "device": device,
                "os": operating_system,
                "depth": target.depth,
            }
        ]
