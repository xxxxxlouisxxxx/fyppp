"""Verified-success-only request deduplication."""

from __future__ import annotations

import hashlib


class SuccessfulDeduplicator:
    """Keeps only keys known to have verified successful responses."""

    def __init__(self) -> None:
        self._successful: set[str] = set()

    @staticmethod
    def key(
        source_category: str,
        provider: str,
        endpoint: str,
        request_hash: str,
        collection_window_id: str,
    ) -> str:
        """Create the mandatory source-aware deduplication key."""
        raw = "\x1f".join(
            (source_category, provider, endpoint, request_hash, collection_window_id)
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def should_skip(self, key: str) -> bool:
        """Return true only for an earlier verified successful response."""
        return key in self._successful

    def record_verified_success(self, key: str) -> None:
        """Make future same-window matching plans eligible for skipping."""
        self._successful.add(key)
