"""Canonical, source-separated collection request identities."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(fields: dict[str, Any]) -> str:
    content = json.dumps(
        fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def serp_request_hash(
    *,
    provider: str,
    search_engine: str,
    search_type: str,
    endpoint: str,
    function: str,
    retrieval_method: str,
    keyword: str,
    location: str,
    language: str,
    device: str,
    operating_system: str,
    depth: int,
    adapter_version: str,
    capability_evidence_version: str,
) -> str:
    """Hash every SERP result-affecting field with an explicit source discriminator."""
    return _digest(locals() | {"source_category": "serp"})


def llm_request_hash(
    *,
    provider: str,
    platform: str,
    model_name: str | None,
    endpoint: str,
    prompt_text: str,
    location: str | None,
    language: str | None,
    options: dict[str, Any],
    adapter_version: str,
    capability_evidence_version: str,
) -> str:
    """Hash LLM dimensions without importing unverified SERP-only fields."""
    return _digest(locals() | {"source_category": "llm"})
