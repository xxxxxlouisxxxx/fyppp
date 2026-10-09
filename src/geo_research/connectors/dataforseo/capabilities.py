"""Evidence-gated provider capabilities.

This module intentionally has no endpoint values while the API evidence register
is unverified or blocked.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from geo_research.connectors.dataforseo.errors import CapabilityNotVerifiedError

CapabilityState = Literal["unverified", "verified", "blocked"]


class CapabilityEvidence(BaseModel):
    """Official-evidence checklist required before an adapter can execute."""

    model_config = ConfigDict(strict=True)

    capability_key: str
    capability_state: CapabilityState
    evidence_version: str = "unverified"
    endpoint: str | None = None
    http_method: str | None = None
    required_fields: tuple[str, ...] = Field(default_factory=tuple)
    fixture_available: bool = False

    def require_verified(self) -> None:
        """Refuse execution unless all required evidence has been reviewed."""
        ready = (
            self.capability_state == "verified"
            and self.endpoint is not None
            and self.http_method is not None
            and bool(self.required_fields)
            and self.fixture_available
        )
        if not ready:
            raise CapabilityNotVerifiedError(
                f"Capability {self.capability_key} is not verified for execution"
            )


def unverified_capability(key: str) -> CapabilityEvidence:
    """Construct an explicit non-executable capability from missing evidence."""
    return CapabilityEvidence(capability_key=key, capability_state="unverified")
