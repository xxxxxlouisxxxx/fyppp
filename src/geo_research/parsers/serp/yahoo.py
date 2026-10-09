"""Yahoo Organic mapping; never falls back to Google or Bing fields."""

from __future__ import annotations

from typing import Any

from geo_research.parsers.serp.base import OrganicSERPParser


class YahooOrganicParser(OrganicSERPParser):
    engine = "yahoo"
    parser_name = "yahoo_organic"

    def parse_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        raw_type = item.get("type")
        if not isinstance(raw_type, str):
            return None
        return {
            "raw_item_type": raw_type,
            "rank_group": item.get("rank_group"),
            "rank_absolute": item.get("rank_absolute"),
            "url": item.get("url"),
            "domain": item.get("domain"),
            "title": item.get("title"),
            "description": item.get("description"),
        }
