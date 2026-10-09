"""Shared mechanics for deliberately isolated engine parser mappings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OrganicSERPParser(ABC):
    parser_version = "1"
    rank_semantics_version = "1"
    engine: str
    parser_name: str

    @abstractmethod
    def parse_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Return this engine's explicit top-level mapping or None when malformed."""
