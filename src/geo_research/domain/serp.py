"""SERP query and target registry models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from geo_research.domain.identifiers import RegistryIdentifier


class RegistryModel(BaseModel):
    """Strict base for all user-managed registry records."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Query(RegistryModel):
    query_id: RegistryIdentifier
    keyword: str = Field(min_length=1)
    language: str = Field(pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*$")
    market: str = Field(pattern=r"^[A-Za-z0-9-]{2,16}$")
    active: bool


class SearchTarget(RegistryModel):
    search_target_id: RegistryIdentifier
    provider: str = Field(min_length=1)
    search_engine: str = Field(min_length=1)
    search_type: str = Field(min_length=1)
    retrieval_method: Literal["TO_BE_VERIFIED", "standard", "live"]
    location_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    language_code: str = Field(pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*$")
    device: str = Field(min_length=1)
    operating_system: str = Field(min_length=1)
    depth: int = Field(gt=0)
    active: bool

    @model_validator(mode="after")
    def provider_must_differ_from_engine(self) -> SearchTarget:
        if self.provider.casefold() == self.search_engine.casefold():
            raise ValueError("provider must be distinct from search_engine")
        return self
