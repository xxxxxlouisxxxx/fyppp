"""Typed Phase 8 SERP parser outputs without provider response assumptions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchObservation:
    observation_id: str
    query_id: str
    provider: str
    search_engine: str
    search_type: str
    location_code: str
    language_code: str
    device: str
    collection_window: str
    response_id: str
    source_ingestion_id: str
    raw_file_hash: str
    has_results: bool
    outcome_status: str


@dataclass(frozen=True, slots=True)
class SERPItem:
    serp_item_id: str
    observation_id: str
    engine: str
    response_id: str
    source_ingestion_id: str
    raw_file_hash: str
    item_index: int
    raw_item_type: str | None
    normalized_item_type: str
    rank_group: int | None
    rank_absolute: int | None
    page: int | None
    position: int | None
    raw_domain: str | None
    normalized_domain: str | None
    raw_url: str | None
    canonical_url: str | None
    title: str | None
    description: str | None
    raw_item_json: str
    parser_name: str
    parser_version: str
    rank_semantics_version: str
    normalization_status: str
    parsing_warning: str | None


@dataclass(frozen=True, slots=True)
class SERPParsingQuarantine:
    quarantine_id: str
    observation_id: str
    engine: str
    response_id: str
    source_ingestion_id: str
    raw_file_hash: str
    item_index: int | None
    reason: str
    raw_item_json: str | None
    parser_name: str
    parser_version: str


@dataclass(frozen=True, slots=True)
class SERPParseResult:
    observation: SearchObservation
    items: tuple[SERPItem, ...]
    quarantine: tuple[SERPParsingQuarantine, ...]
