"""Explicit source-to-execution-target registry mappings."""

from __future__ import annotations

from geo_research.domain.identifiers import RegistryIdentifier
from geo_research.domain.serp import RegistryModel


class QueryTargetAssignment(RegistryModel):
    """An intentional mapping from one query to one SERP target."""

    assignment_id: RegistryIdentifier
    query_id: RegistryIdentifier
    search_target_id: RegistryIdentifier
    active: bool


class PromptTargetAssignment(RegistryModel):
    """An intentional mapping from one prompt to one LLM target."""

    assignment_id: RegistryIdentifier
    prompt_id: RegistryIdentifier
    llm_target_id: RegistryIdentifier
    active: bool
