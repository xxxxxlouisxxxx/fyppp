"""Shared constrained registry values."""

from __future__ import annotations

from enum import StrEnum


class SearchType(StrEnum):
    """Supported research search types for the current contract."""

    ORGANIC = "organic"


class RetrievalMethod(StrEnum):
    """Retrieval modes identified by the registry, not API support claims."""

    TO_BE_VERIFIED = "TO_BE_VERIFIED"
    LIVE = "live"
    STANDARD = "standard"
