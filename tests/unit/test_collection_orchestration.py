from __future__ import annotations

from datetime import UTC, datetime

import pytest

from geo_research.collection.budget import BudgetPolicy, BudgetTracker
from geo_research.collection.deduplication import SuccessfulDeduplicator
from geo_research.collection.identity import llm_request_hash, serp_request_hash
from geo_research.collection.manifest import RunManifest
from geo_research.collection.retry_policy import RetryDecision, decide_retry
from geo_research.collection.serp_collector import SERPCollector, SERPPlan
from geo_research.collection.state_machine import CollectionState, StateMachine


def serp_hash(engine: str = "google", location: str = "2840") -> str:
    return serp_request_hash(
        provider="dataforseo",
        search_engine=engine,
        search_type="organic",
        endpoint="verified-endpoint",
        function="verified-function",
        retrieval_method="live",
        keyword="same text",
        location=location,
        language="en",
        device="desktop",
        operating_system="windows",
        depth=10,
        adapter_version="v1",
        capability_evidence_version="v1",
    )


def test_request_identity_separates_sources_targets_windows_and_location() -> None:
    google = serp_hash()
    assert google != serp_hash("bing")
    assert google != serp_hash(location="2124")
    assert google != llm_request_hash(
        provider="dataforseo",
        platform="chatgpt",
        model_name=None,
        endpoint="verified-endpoint",
        prompt_text="same text",
        location="2840",
        language="en",
        options={},
        adapter_version="v1",
        capability_evidence_version="v1",
    )


def test_deduplication_skips_only_verified_success_in_same_window() -> None:
    deduplicator = SuccessfulDeduplicator()
    key = deduplicator.key("serp", "dataforseo", "endpoint", serp_hash(), "window-1")
    assert deduplicator.should_skip(key) is False
    deduplicator.record_verified_success(key)
    assert deduplicator.should_skip(key) is True
    next_window = deduplicator.key(
        "serp", "dataforseo", "endpoint", serp_hash(), "window-2"
    )
    assert deduplicator.should_skip(next_window) is False


def test_budget_blocks_caps_and_unknown_estimated_cost_under_strict_policy() -> None:
    tracker = BudgetTracker(
        BudgetPolicy(per_request_usd=1.0, per_run_usd=1.5, unknown_cost_policy="block")
    )
    assert tracker.authorize("google", "google", None) is False
    assert tracker.authorize("google", "google", 2.0) is False
    assert tracker.authorize("google", "google", 1.0) is True
    tracker.record_actual_cost(1.2)
    assert tracker.total_actual_usd == 1.2


@pytest.mark.parametrize(
    ("status", "after_post", "expected"),
    [
        (401, False, RetryDecision.NO_RETRY),
        (402, False, RetryDecision.NO_RETRY),
        (403, False, RetryDecision.NO_RETRY),
        (429, False, RetryDecision.NO_RETRY),
        (503, False, RetryDecision.RETRY),
        (None, True, RetryDecision.OUTCOME_UNKNOWN),
    ],
)
def test_retry_policy(
    status: int | None, after_post: bool, expected: RetryDecision
) -> None:
    assert (
        decide_retry(
            status_code=status,
            timeout_after_post=after_post,
            provider_retry_supported=False,
        )
        == expected
    )


def test_state_machine_disallows_outcome_unknown_resend() -> None:
    machine = StateMachine()
    machine.transition(CollectionState.SENDING)
    machine.transition(CollectionState.OUTCOME_UNKNOWN)
    with pytest.raises(ValueError):
        machine.transition(CollectionState.SENDING)


def test_manifest_tracks_partial_success_and_actual_cost() -> None:
    manifest = RunManifest(run_id="run-1", started_at=datetime(2026, 9, 25, tzinfo=UTC))
    manifest.record(CollectionState.SUCCESS, actual_cost_usd=1.25)
    manifest.record(CollectionState.FAILED)
    assert manifest.status == "partial_success"
    assert manifest.actual_cost_usd == 1.25


def collection_plan(
    *,
    deduplicator: SuccessfulDeduplicator | None = None,
    verified: bool = True,
    estimate: float | None = 1.0,
) -> SERPPlan:
    deduplicator = deduplicator or SuccessfulDeduplicator()
    request_hash = serp_hash()
    return SERPPlan(
        query_id="query-1",
        target_id="target-1",
        provider="dataforseo",
        endpoint="verified-endpoint",
        request_hash=request_hash,
        deduplication_key=deduplicator.key(
            "serp", "dataforseo", "verified-endpoint", request_hash, "window-1"
        ),
        estimated_cost_usd=estimate,
        capability_verified=verified,
        safe_payload={"keyword": "same text"},
        expected_raw_path="raw/expected",
        search_engine="google",
    )


def test_collector_never_calls_executor_when_dry_or_unverified() -> None:
    calls = 0

    def execute() -> tuple[dict[str, object], float | None]:
        nonlocal calls
        calls += 1
        return {}, 1.0

    collector = SERPCollector(
        SuccessfulDeduplicator(),
        BudgetTracker(BudgetPolicy(unknown_cost_policy="block")),
    )
    manifest = RunManifest("run-1", datetime(2026, 9, 25, tzinfo=UTC))
    assert (
        collector.collect(collection_plan(), manifest, execute, dry_run=True)
        == CollectionState.NOT_SENT
    )
    assert (
        collector.collect(collection_plan(verified=False), manifest, execute)
        == CollectionState.BLOCKED_UNVERIFIED
    )
    assert calls == 0


def test_collector_finalizes_before_success_and_deduplicates_afterward() -> None:
    deduplicator = SuccessfulDeduplicator()
    collector = SERPCollector(deduplicator, BudgetTracker(BudgetPolicy()))
    manifest = RunManifest("run-1", datetime(2026, 9, 25, tzinfo=UTC))
    plan = collection_plan(deduplicator=deduplicator)
    events: list[str] = []

    def execute() -> tuple[dict[str, object], float | None]:
        events.append("execute")
        return {"response": "ok"}, 1.25

    def finalize(response: dict[str, object]) -> None:
        assert response == {"response": "ok"}
        events.append("finalize")

    assert (
        collector.collect(plan, manifest, execute, finalize_response=finalize)
        == CollectionState.SUCCESS
    )
    assert events == ["execute", "finalize"]
    assert (
        collector.collect(plan, manifest, execute) == CollectionState.SKIPPED_DUPLICATE
    )
