"""Explicit user-reviewed instrument mappings; independent of brand selection."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from geo_research.domain.identifiers import RegistryIdentifier
from geo_research.domain.serp import RegistryModel


class Comparison(RegistryModel):
    comparison_id: RegistryIdentifier
    query_id: RegistryIdentifier
    prompt_id: RegistryIdentifier
    active: bool
    mapping_version: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    approval_date: date
    reason: str = Field(min_length=1)
    effective_start_date: date
    effective_end_date: date | None
    scope: Literal["matched_locale_window"]

    @model_validator(mode="after")
    def validate_approval(self) -> Comparison:
        if any(not value.strip() for value in (
            self.mapping_version, self.reviewer, self.reason,
        )):
            raise ValueError("mapping approval fields must not be blank")
        if (self.effective_end_date
            and self.effective_end_date < self.effective_start_date):
            raise ValueError("invalid mapping effective date range")
        return self