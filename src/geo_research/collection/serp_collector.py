"""Injected SERP collection orchestration; it owns neither adapters nor HTTP clients."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from geo_research.collection.budget import BudgetTracker
from geo_research.collection.deduplication import SuccessfulDeduplicator
from geo_research.collection.manifest import RunManifest
from geo_research.collection.state_machine import CollectionState


@dataclass(frozen=True, slots=True)
class SERPPlan:
    query_id: str
    target_id: str
    provider: str
    endpoint: str | None
    request_hash: str
    deduplication_key: str
    estimated_cost_usd: float | None
    capability_verified: bool
    safe_payload: dict[str, Any]
    expected_raw_path: str
    search_engine: str | None = None


class SERPCollector:
    """Runs injected SERP executors only after capability, dedup, and budget checks."""

    def __init__(
        self, deduplicator: SuccessfulDeduplicator, budget: BudgetTracker
    ) -> None:
        self.deduplicator = deduplicator
        self.budget = budget

    def collect(
        self,
        plan: SERPPlan,
        manifest: RunManifest,
        execute: Callable[[], tuple[dict[str, Any], float | None]],
        *,
        dry_run: bool = False,
        finalize_response: Callable[[dict[str, Any]], None] | None = None,
    ) -> CollectionState:
        if dry_run:
            manifest.record(
                CollectionState.NOT_SENT, estimated_cost_usd=plan.estimated_cost_usd
            )
            return CollectionState.NOT_SENT
        if not plan.capability_verified:
            manifest.record(CollectionState.BLOCKED_UNVERIFIED)
            return CollectionState.BLOCKED_UNVERIFIED
        if self.deduplicator.should_skip(plan.deduplication_key):
            manifest.record(CollectionState.SKIPPED_DUPLICATE)
            return CollectionState.SKIPPED_DUPLICATE
        if not self.budget.authorize(
            plan.target_id, plan.search_engine or "", plan.estimated_cost_usd
        ):
            manifest.record(CollectionState.BLOCKED_BUDGET)
            return CollectionState.BLOCKED_BUDGET
        response_payload, actual_cost = execute()
        if finalize_response is not None:
            finalize_response(response_payload)
        self.budget.record_actual_cost(actual_cost)
        self.deduplicator.record_verified_success(plan.deduplication_key)
        manifest.record(
            CollectionState.SUCCESS,
            estimated_cost_usd=plan.estimated_cost_usd,
            actual_cost_usd=actual_cost,
        )
        return CollectionState.SUCCESS
