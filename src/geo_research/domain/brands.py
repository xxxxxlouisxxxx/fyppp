"""Brand, alias, and domain registry models."""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from geo_research.domain.identifiers import RegistryIdentifier
from geo_research.domain.serp import RegistryModel


class EffectiveDatedBrandRecord(RegistryModel):
    market: str = Field(pattern=r"^[A-Za-z0-9-]{2,16}$")
    language: str = Field(pattern=r"^[A-Za-z]{2,8}$")
    effective_start_date: date
    effective_end_date: date | None = None

    @model_validator(mode="after")
    def date_range_is_valid(self) -> EffectiveDatedBrandRecord:
        if (
            self.effective_end_date
            and self.effective_end_date < self.effective_start_date
        ):
            raise ValueError("invalid effective date range")
        return self


class Brand(EffectiveDatedBrandRecord):
    brand_id: RegistryIdentifier
    canonical_name: str = Field(min_length=1)
    ownership_type: str = Field(min_length=1)
    active: bool


class BrandAlias(EffectiveDatedBrandRecord):
    brand_alias_id: RegistryIdentifier
    brand_id: RegistryIdentifier
    alias_text: str = Field(min_length=1)


class BrandDomain(EffectiveDatedBrandRecord):
    brand_domain_id: RegistryIdentifier
    brand_id: RegistryIdentifier
    domain: str = Field(pattern=r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$")
