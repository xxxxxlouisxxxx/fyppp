"""Minimal provider envelope preservation contract without field assumptions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from geo_research.connectors.dataforseo.errors import DataForSEOResponseError


class ProviderEnvelope(BaseModel):
    """A JSON-object envelope retained without interpreting undocumented fields."""

    model_config = ConfigDict(extra="allow", strict=True)

    payload: dict[str, Any]
    provider_request_id: str | None = None
    correlation_id: str


def parse_envelope(
    payload: object, correlation_id: str, provider_request_id: str | None
) -> ProviderEnvelope:
    """Accept only a top-level JSON object.

    Provider schema interpretation is deferred.
    """
    if not isinstance(payload, dict):
        raise DataForSEOResponseError(
            f"Malformed provider envelope; correlation_id={correlation_id}"
        )
    return ProviderEnvelope(
        payload=payload,
        provider_request_id=provider_request_id,
        correlation_id=correlation_id,
    )
