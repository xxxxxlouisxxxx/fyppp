"""Legal collection attempt state transitions."""

from __future__ import annotations

from enum import StrEnum


class CollectionState(StrEnum):
    PLANNED = "planned"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    BLOCKED_UNVERIFIED = "blocked_unverified"
    BLOCKED_BUDGET = "blocked_budget"
    NOT_SENT = "not_sent"
    SENDING = "sending"
    SENT = "sent"
    SUCCESS = "success"
    FAILED = "failed"
    RESPONSE_INVALID = "response_invalid"
    OUTCOME_UNKNOWN = "outcome_unknown"


_ALLOWED: dict[CollectionState, set[CollectionState]] = {
    CollectionState.PLANNED: {
        CollectionState.SKIPPED_DUPLICATE,
        CollectionState.BLOCKED_UNVERIFIED,
        CollectionState.BLOCKED_BUDGET,
        CollectionState.NOT_SENT,
        CollectionState.SENDING,
    },
    CollectionState.SENDING: {
        CollectionState.SENT,
        CollectionState.FAILED,
        CollectionState.OUTCOME_UNKNOWN,
    },
    CollectionState.SENT: {
        CollectionState.SUCCESS,
        CollectionState.FAILED,
        CollectionState.RESPONSE_INVALID,
        CollectionState.OUTCOME_UNKNOWN,
    },
}


class StateMachine:
    """Enforces terminal collection states, especially no resend of unknown outcomes."""

    def __init__(self) -> None:
        self.state = CollectionState.PLANNED

    def transition(self, next_state: CollectionState) -> None:
        """Apply one legal transition or reject an invalid orchestration action."""
        if next_state not in _ALLOWED.get(self.state, set()):
            raise ValueError(f"illegal transition: {self.state} -> {next_state}")
        self.state = next_state
