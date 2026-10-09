"""Explicit collection budget and unknown-cost policy."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

UnknownCostPolicy = Literal["block", "allow"]


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    per_request_usd: float | None = None
    per_target_usd: float | None = None
    per_engine_usd: float | None = None
    per_platform_usd: float | None = None
    per_run_usd: float | None = None
    daily_usd: float | None = None
    unknown_cost_policy: UnknownCostPolicy = "block"
    cli_max_cost_usd: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "per_request_usd", "per_target_usd", "per_engine_usd",
            "per_platform_usd", "per_run_usd", "daily_usd", "cli_max_cost_usd",
        ):
            value = getattr(self, name)
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.unknown_cost_policy not in {"allow", "block"}:
            raise ValueError("invalid unknown cost policy")


class BudgetTracker:
    """Authorizes estimates and records actual costs separately from estimates."""

    def __init__(self, policy: BudgetPolicy) -> None:
        self.policy = policy
        self.total_estimated_usd = 0.0
        self.total_actual_usd = 0.0
        self._target_estimates: dict[str, float] = {}
        self._dimension_estimates: dict[tuple[str, str], float] = {}

    def authorize(
        self, target_id: str, target_dimension: str, estimate: float | None,
        *, source_category: Literal["serp", "llm"] = "serp",
    ) -> bool:
        """Approve a request only when its known estimate fits every applicable cap."""
        # A configured daily cap requires a shared persistent ledger. This local
        # tracker cannot certify daily spend across runs, so it fails closed.
        if self.policy.daily_usd is not None:
            return False
        all_caps = (
            self.policy.per_request_usd, self.policy.cli_max_cost_usd,
            self.policy.per_run_usd, self.policy.per_target_usd,
            self.policy.per_engine_usd, self.policy.per_platform_usd,
        )
        if estimate is None:
            return (self.policy.unknown_cost_policy == "allow"
                    and all(cap is None for cap in all_caps))
        if not isfinite(estimate) or estimate < 0:
            return False
        if source_category not in {"serp", "llm"} or not target_dimension:
            return False
        caps = (self.policy.per_request_usd,)
        if any(cap is not None and estimate > cap for cap in caps):
            return False
        if (
            any(cap is not None
                and max(self.total_estimated_usd, self.total_actual_usd)
                + estimate > cap
                for cap in (self.policy.per_run_usd, self.policy.cli_max_cost_usd))
        ):
            return False
        current_target = self._target_estimates.get(target_id, 0.0)
        target_cap = self.policy.per_target_usd
        if target_cap is not None and current_target + estimate > target_cap:
            return False
        dimension_key = (source_category, target_dimension)
        current_dimension = self._dimension_estimates.get(dimension_key, 0.0)
        dimension_cap = (self.policy.per_engine_usd if source_category == "serp"
                 else self.policy.per_platform_usd)
        if (dimension_cap is not None
            and current_dimension + estimate > dimension_cap):
            return False
        self.total_estimated_usd += estimate
        self._target_estimates[target_id] = current_target + estimate
        self._dimension_estimates[dimension_key] = current_dimension + estimate
        return True

    def record_actual_cost(self, actual_cost: float | None) -> None:
        """Record actual cost without coercing an unknown value to zero."""
        if actual_cost is not None:
            if not isfinite(actual_cost) or actual_cost < 0:
                raise ValueError("actual cost must be finite and nonnegative")
            self.total_actual_usd += actual_cost
