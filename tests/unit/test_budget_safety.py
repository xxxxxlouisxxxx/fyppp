from __future__ import annotations

import pytest

from geo_research.collection.budget import BudgetPolicy, BudgetTracker


@pytest.mark.parametrize("amount", [-1., float("inf"), float("nan")])
def test_invalid_caps_estimates_actuals(amount):
    with pytest.raises(ValueError):
        BudgetPolicy(per_run_usd=amount)
    tracker = BudgetTracker(BudgetPolicy())
    assert not tracker.authorize("target", "google", amount)
    with pytest.raises(ValueError):
        tracker.record_actual_cost(amount)


def test_dimension_accumulates_across_targets_and_zero_cap():
    tracker = BudgetTracker(BudgetPolicy(per_engine_usd=1., per_platform_usd=2.))
    assert tracker.authorize("target-a", "google", .6)
    assert not tracker.authorize("target-b", "google", .5)
    assert tracker.authorize("target-b", "bing", .5)
    assert tracker.authorize("llm-a", "gemini", 1.5, source_category="llm")
    assert not tracker.authorize("llm-b", "gemini", .6, source_category="llm")
    assert not BudgetTracker(BudgetPolicy(per_engine_usd=0)).authorize("x", "g", .01)


def test_cli_is_run_cap_actual_overrun_blocks_next_request():
    tracker = BudgetTracker(BudgetPolicy(cli_max_cost_usd=1.))
    assert tracker.authorize("a", "google", .6)
    assert not tracker.authorize("b", "google", .6)
    tracker.record_actual_cost(1.2)
    assert not tracker.authorize("b", "google", 0)


def test_unknown_cannot_bypass_caps_daily_requires_shared_ledger():
    tracker = BudgetTracker(BudgetPolicy(per_run_usd=1., unknown_cost_policy="allow"))
    assert not tracker.authorize("a", "google", None)
    assert BudgetTracker(BudgetPolicy(unknown_cost_policy="allow")).authorize(
        "a", "google", None,
    )
    tracker = BudgetTracker(BudgetPolicy(daily_usd=5.))
    assert not tracker.authorize("a", "google", .1)


def test_missing_dimension_does_not_claim_engine_coverage():
    assert not BudgetTracker(BudgetPolicy()).authorize("a", "", 1.)