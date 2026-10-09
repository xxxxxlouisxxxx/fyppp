"""Separate SERP adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from geo_research.connectors.dataforseo.capabilities import CapabilityEvidence
from geo_research.domain.serp import Query, SearchTarget


class SERPAdapterRequest(BaseModel):
    """An executable provider request only after capability evidence is verified."""

    model_config = ConfigDict(strict=True)

    endpoint: str
    payload: dict[str, Any] | list[dict[str, Any]]
    identity: dict[str, str]
    capability_evidence_version: str


class SERPAdapter(ABC):
    """Converts a query and search target without storing or parsing evidence."""

    capability: CapabilityEvidence
    search_engine: str

    def build_payload(self, query: Query, target: SearchTarget) -> SERPAdapterRequest:
        """Build only a capability-approved request; otherwise fail closed."""
        self.capability.require_verified()
        if target.search_engine.casefold() != self.search_engine:
            raise ValueError("search target does not match adapter search engine")
        return SERPAdapterRequest(
            endpoint=self.capability.endpoint or "",
            payload=self._build_verified_payload(query, target),
            identity={
                "query_id": query.query_id,
                "search_target_id": target.search_target_id,
                "provider": target.provider,
                "search_engine": target.search_engine,
                "search_type": target.search_type,
                "retrieval_method": target.retrieval_method,
                "location_code": target.location_code,
                "language_code": target.language_code,
                "device": target.device,
                "operating_system": target.operating_system,
            },
            capability_evidence_version=self.capability.evidence_version,
        )

    @abstractmethod
    def _build_verified_payload(
        self, query: Query, target: SearchTarget
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Implement only after provider required-field evidence has been verified."""
