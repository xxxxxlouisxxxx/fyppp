"""LLM prompt and target registry models."""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from geo_research.domain.identifiers import RegistryIdentifier
from geo_research.domain.serp import RegistryModel


class LLMPrompt(RegistryModel):
    prompt_id: RegistryIdentifier
    prompt_text: str = Field(min_length=1)
    language: str = Field(pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*$")
    market: str = Field(pattern=r"^[A-Za-z0-9-]{2,16}$")
    active: bool


class LLMTarget(RegistryModel):
    llm_target_id: RegistryIdentifier
    provider: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    endpoint_name: str = Field(min_length=1)
    location_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    language_code: str = Field(pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*$")
    active: bool

    @model_validator(mode="after")
    def provider_must_differ_from_platform(self) -> LLMTarget:
        if self.provider.casefold() == self.platform.casefold():
            raise ValueError("provider must be distinct from platform")
        return self

    @field_validator("model_name")
    @classmethod
    def model_must_be_verified_or_unverified_placeholder(cls, value: str) -> str:
        if value not in {"TO_BE_VERIFIED", "chat_gpt", "gemini"}:
            raise ValueError("model_name is not a verified LLM target")
        return value
