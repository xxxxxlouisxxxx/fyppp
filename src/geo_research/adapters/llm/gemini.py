"""Gemini contract, intentionally non-executable pending official evidence."""

from __future__ import annotations

from typing import Any

from geo_research.adapters.llm.base import LLMAdapter
from geo_research.connectors.dataforseo.capabilities import unverified_capability
from geo_research.domain.llm import LLMPrompt, LLMTarget


class GeminiAdapter(LLMAdapter):
    capability = unverified_capability("llm.gemini")
    platform = "gemini"

    def _build_verified_payload(
        self, prompt: LLMPrompt, target: LLMTarget
    ) -> dict[str, Any]:
        raise NotImplementedError("Official Gemini target evidence is required")
