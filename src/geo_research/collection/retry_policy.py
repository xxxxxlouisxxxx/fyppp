"""Retry classification without automatic resend of ambiguous POST outcomes."""

from __future__ import annotations

from enum import StrEnum


class RetryDecision(StrEnum):
    NO_RETRY = "no_retry"
    RETRY = "retry"
    OUTCOME_UNKNOWN = "outcome_unknown"


def decide_retry(
    *,
    status_code: int | None,
    timeout_after_post: bool,
    provider_retry_supported: bool,
) -> RetryDecision:
    """Classify one failure according to the evidence-safe retry policy."""
    if timeout_after_post:
        return RetryDecision.OUTCOME_UNKNOWN
    if status_code in {401, 402, 403}:
        return RetryDecision.NO_RETRY
    if status_code == 429:
        return (
            RetryDecision.RETRY if provider_retry_supported else RetryDecision.NO_RETRY
        )
    if status_code in {500, 503}:
        return RetryDecision.RETRY
    return RetryDecision.NO_RETRY
