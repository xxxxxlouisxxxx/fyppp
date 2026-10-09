"""Separate LLM adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from geo_research.connectors.dataforseo.capabilities import CapabilityEvidence
from geo_research.domain.llm import LLMPrompt, LLMTarget


class LLMAdapterRequest(BaseModel):
    """An executable LLM request only after capability evidence is verified."""

    model_config = ConfigDict(strict=True)

    endpoint: str
    payload: dict[str, Any]
    identity: dict[str, str]
    capability_evidence_version: str


class LLMAdapter(ABC):
    """Converts prompt/LLM-target inputs without sharing SERP-specific dimensions."""

    capability: CapabilityEvidence
    platform: str

    def build_payload(self, prompt: LLMPrompt, target: LLMTarget) -> LLMAdapterRequest:
        """Build only a capability-approved LLM request; otherwise fail closed."""
        self.capability.require_verified()
        if target.platform.casefold() != self.platform:
            raise ValueError("LLM target does not match adapter platform")
        return LLMAdapterRequest(
            endpoint=self.capability.endpoint or "",
            payload=self._build_verified_payload(prompt, target),
            identity={
                "prompt_id": prompt.prompt_id,
                "llm_target_id": target.llm_target_id,
                "provider": target.provider,
                "platform": target.platform,
                "model_name": target.model_name,
                "location_code": target.location_code,
                "language_code": target.language_code,
            },
            capability_evidence_version=self.capability.evidence_version,
        )

    @abstractmethod
    def _build_verified_payload(
        self, prompt: LLMPrompt, target: LLMTarget
    ) -> dict[str, Any]:
        """Implement only after LLM Scraper request-field evidence is verified."""
