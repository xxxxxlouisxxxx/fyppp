"""Run-level collection manifest accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from geo_research.collection.state_machine import CollectionState


@dataclass(slots=True)
class RunManifest:
    """Counts outcomes and separates estimate/actual cost totals for one run."""

    run_id: str
    started_at: datetime
    counts: dict[str, int] = field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0

    def record(
        self,
        state: CollectionState,
        *,
        estimated_cost_usd: float | None = None,
        actual_cost_usd: float | None = None,
    ) -> None:
        self.counts[state.value] = self.counts.get(state.value, 0) + 1
        if estimated_cost_usd is not None:
            self.estimated_cost_usd += estimated_cost_usd
        if actual_cost_usd is not None:
            self.actual_cost_usd += actual_cost_usd

    @property
    def status(self) -> str:
        successes = self.counts.get(CollectionState.SUCCESS.value, 0)
        failures = self.counts.get(CollectionState.FAILED.value, 0)
        return (
            "partial_success"
            if successes and failures
            else "success"
            if successes
            else "failed"
        )
