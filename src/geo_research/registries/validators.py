"""Registry validation and machine-readable results."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from geo_research.domain.assignments import (
    PromptTargetAssignment,
    QueryTargetAssignment,
)
from geo_research.domain.brands import Brand, BrandAlias, BrandDomain
from geo_research.domain.comparisons import Comparison
from geo_research.domain.llm import LLMPrompt, LLMTarget
from geo_research.domain.serp import Query, SearchTarget


class RegistryValidationError(ValueError):
    """Raised when a registry violates its declared or relational contract."""


class RegistryValidationResult(BaseModel):
    """Serializable result for CLI and automation callers."""

    model_config = ConfigDict(strict=True)

    valid: bool
    counts: dict[str, int]
    assignment_summary: dict[str, dict[str, int]]


REGISTRIES: dict[str, tuple[str, type[BaseModel], str]] = {
    "queries": ("queries.csv", Query, "query_id"),
    "search_targets": ("search_targets.csv", SearchTarget, "search_target_id"),
    "llm_prompts": ("llm_prompts.csv", LLMPrompt, "prompt_id"),
    "llm_targets": ("llm_targets.csv", LLMTarget, "llm_target_id"),
    "query_target_assignments": (
        "query_target_assignments.csv",
        QueryTargetAssignment,
        "assignment_id",
    ),
    "prompt_target_assignments": (
        "prompt_target_assignments.csv",
        PromptTargetAssignment,
        "assignment_id",
    ),
    "brands": ("brands.csv", Brand, "brand_id"),
    "brand_aliases": ("brand_aliases.csv", BrandAlias, "brand_alias_id"),
    "brand_domains": ("brand_domains.csv", BrandDomain, "brand_domain_id"),
}


def _coerce_row(model: type[BaseModel], row: dict[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = dict(row)
    for field_name, field in model.model_fields.items():
        if field.annotation is bool:
            value = values[field_name].casefold()
            if value not in {"true", "false"}:
                raise RegistryValidationError(f"{field_name}: invalid boolean")
            values[field_name] = value == "true"
        elif field_name == "depth":
            try:
                values[field_name] = int(values[field_name])
            except ValueError as error:
                raise RegistryValidationError("depth: invalid integer") from error
        elif field_name.endswith("_date"):
            value = values[field_name]
            values[field_name] = (
                None
                if value == "" and field_name.endswith("end_date")
                else date.fromisoformat(value)
            )
    return values


def _parse_registry(
    directory: Path, filename: str, model: type[BaseModel], identifier: str
) -> list[BaseModel]:
    from geo_research.registries.loaders import load_csv

    rows = load_csv(directory / filename, model.model_fields)
    parsed: list[BaseModel] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        try:
            item = model.model_validate(_coerce_row(model, row), strict=True)
        except (ValidationError, ValueError) as error:
            raise RegistryValidationError(
                f"{filename} row {row_number}: {error}"
            ) from error
        item_id = str(getattr(item, identifier))
        if item_id in seen:
            raise RegistryValidationError(
                f"{filename}: duplicate {identifier}: {item_id}"
            )
        seen.add(item_id)
        parsed.append(item)
    return parsed


def _assert_references(
    items: Iterable[BrandAlias | BrandDomain], brand_ids: set[str]
) -> None:
    for item in items:
        if item.brand_id not in brand_ids:
            raise RegistryValidationError(f"brand_id does not exist: {item.brand_id}")


def _assert_brand_windows(brands: list[Brand]) -> None:
    groups: dict[tuple[str, str, str], list[Brand]] = {}
    for brand in brands:
        groups.setdefault(
            (brand.canonical_name.casefold(), brand.market, brand.language), []
        ).append(brand)
    for records in groups.values():
        for index, left in enumerate(records):
            left_end = left.effective_end_date or date.max
            for right in records[index + 1 :]:
                right_end = right.effective_end_date or date.max
                if (
                    left.effective_start_date <= right_end
                    and right.effective_start_date <= left_end
                ):
                    raise RegistryValidationError(
                        "overlap in brand ownership effective dates"
                    )


def _assert_query_assignments(
    assignments: Iterable[QueryTargetAssignment],
    queries: dict[str, Query],
    search_targets: dict[str, SearchTarget],
) -> None:
    seen_active_pairs: set[tuple[str, str]] = set()
    for assignment in assignments:
        query = queries.get(assignment.query_id)
        target = search_targets.get(assignment.search_target_id)
        if query is None:
            raise RegistryValidationError(
                f"query_id does not exist: {assignment.query_id}"
            )
        if target is None:
            raise RegistryValidationError(
                f"search_target_id does not exist: {assignment.search_target_id}"
            )
        if not assignment.active:
            continue
        pair = (assignment.query_id, assignment.search_target_id)
        if pair in seen_active_pairs:
            raise RegistryValidationError(
                f"duplicate active assignment pair: {pair[0]}, {pair[1]}"
            )
        seen_active_pairs.add(pair)
        if not query.active:
            raise RegistryValidationError("active assignment requires an active source")
        if not target.active:
            raise RegistryValidationError("active assignment requires an active target")


def _assert_prompt_assignments(
    assignments: Iterable[PromptTargetAssignment],
    prompts: dict[str, LLMPrompt],
    llm_targets: dict[str, LLMTarget],
) -> None:
    seen_active_pairs: set[tuple[str, str]] = set()
    resolved_prompt_assignments: list[
        tuple[PromptTargetAssignment, LLMPrompt, LLMTarget]
    ] = []
    for assignment in assignments:
        prompt = prompts.get(assignment.prompt_id)
        target = llm_targets.get(assignment.llm_target_id)
        if prompt is None:
            raise RegistryValidationError(
                f"prompt_id does not exist: {assignment.prompt_id}"
            )
        if target is None:
            raise RegistryValidationError(
                f"llm_target_id does not exist: {assignment.llm_target_id}"
            )
        resolved_prompt_assignments.append((assignment, prompt, target))
        if not assignment.active:
            continue
        pair = (assignment.prompt_id, assignment.llm_target_id)
        if pair in seen_active_pairs:
            raise RegistryValidationError(
                f"duplicate active assignment pair: {pair[0]}, {pair[1]}"
            )
        seen_active_pairs.add(pair)
    for assignment, prompt, target in resolved_prompt_assignments:
        if not assignment.active:
            continue
        if not prompt.active:
            raise RegistryValidationError("active assignment requires an active source")
        if not target.active:
            raise RegistryValidationError("active assignment requires an active target")
        if target.model_name == "TO_BE_VERIFIED":
            raise RegistryValidationError(
                "active prompt assignment cannot use model_name=TO_BE_VERIFIED"
            )


def _count_assignment_dimensions(
    query_assignments: Iterable[QueryTargetAssignment],
    prompt_assignments: Iterable[PromptTargetAssignment],
    queries: dict[str, Query],
    search_targets: dict[str, SearchTarget],
    prompts: dict[str, LLMPrompt],
    llm_targets: dict[str, LLMTarget],
) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {
        "provider": {},
        "search_engine": {},
        "platform": {},
        "market": {},
        "active": {},
    }

    def increment(dimension: str, value: str) -> None:
        values = summary[dimension]
        values[value] = values.get(value, 0) + 1

    for query_assignment in query_assignments:
        search_target = search_targets[query_assignment.search_target_id]
        query = queries[query_assignment.query_id]
        increment("provider", search_target.provider)
        increment("search_engine", search_target.search_engine)
        increment("market", query.market)
        increment("active", str(query_assignment.active).lower())
    for prompt_assignment in prompt_assignments:
        llm_target = llm_targets[prompt_assignment.llm_target_id]
        prompt = prompts[prompt_assignment.prompt_id]
        increment("provider", llm_target.provider)
        increment("platform", llm_target.platform)
        increment("market", prompt.market)
        increment("active", str(prompt_assignment.active).lower())
    return summary


def validate_registries(directory: Path) -> RegistryValidationResult:
    """Validate all registry CSVs and their explicit cross-registry references."""
    parsed = {
        name: _parse_registry(directory, filename, model, identifier)
        for name, (filename, model, identifier) in REGISTRIES.items()
    }
    query_rows = cast(list[Query], parsed["queries"])
    prompt_rows = cast(list[LLMPrompt], parsed["llm_prompts"])
    search_target_rows = cast(list[SearchTarget], parsed["search_targets"])
    llm_target_rows = cast(list[LLMTarget], parsed["llm_targets"])
    query_assignment_rows = cast(
        list[QueryTargetAssignment], parsed["query_target_assignments"]
    )
    prompt_assignment_rows = cast(
        list[PromptTargetAssignment], parsed["prompt_target_assignments"]
    )
    brand_rows = cast(list[Brand], parsed["brands"])
    alias_rows = cast(list[BrandAlias], parsed["brand_aliases"])
    domain_rows = cast(list[BrandDomain], parsed["brand_domains"])
    queries = {item.query_id: item for item in query_rows}
    prompts = {item.prompt_id: item for item in prompt_rows}
    search_targets = {item.search_target_id: item for item in search_target_rows}
    llm_targets = {item.llm_target_id: item for item in llm_target_rows}
    brand_ids = {item.brand_id for item in brand_rows}
    _assert_references(alias_rows, brand_ids)
    _assert_references(domain_rows, brand_ids)
    _assert_brand_windows(brand_rows)
    _assert_query_assignments(query_assignment_rows, queries, search_targets)
    _assert_prompt_assignments(prompt_assignment_rows, prompts, llm_targets)
    # Optional for legacy fixture registries; absent means no approved comparisons.
    if (directory / "comparisons.csv").exists():
        comparisons = load_comparisons(directory)
        parsed["comparisons"] = comparisons
    return RegistryValidationResult(
        valid=True,
        counts={name: len(items) for name, items in parsed.items()},
        assignment_summary=_count_assignment_dimensions(
            query_assignment_rows,
            prompt_assignment_rows,
            queries,
            search_targets,
            prompts,
            llm_targets,
        ),
    )


def load_comparisons(directory: Path) -> list[Comparison]:
    """Validate explicit mappings; never pair by suffix automatically at runtime."""
    comparisons = cast(list[Comparison], _parse_registry(
        directory, "comparisons.csv", Comparison, "comparison_id",
    ))
    queries = {row.query_id: row for row in cast(list[Query], _parse_registry(
        directory, "queries.csv", Query, "query_id",
    ))}
    prompts = {row.prompt_id: row for row in cast(list[LLMPrompt], _parse_registry(
        directory, "llm_prompts.csv", LLMPrompt, "prompt_id",
    ))}
    pairs: set[tuple[str, str]] = set()
    for mapping in comparisons:
        query, prompt = queries.get(mapping.query_id), prompts.get(mapping.prompt_id)
        if query is None or prompt is None:
            raise RegistryValidationError("comparison references unknown query/prompt")
        if mapping.active:
            pair = (mapping.query_id, mapping.prompt_id)
            if pair in pairs:
                raise RegistryValidationError("duplicate active comparison pair")
            pairs.add(pair)
            if not query.active or not prompt.active:
                raise RegistryValidationError(
                    "active comparison requires active instruments"
                )
            if query.language.casefold() != prompt.language.casefold():
                raise RegistryValidationError("comparison instrument languages differ")
    return comparisons
