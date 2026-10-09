"""Run and attempt identity models; no collection transport is created here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class CollectionAttempt:
    attempt_id: str
    attempt_number: int
    previous_attempt_id: str | None


class RunManager:
    """Generates UTC run and linked-attempt identities."""

    def create_run_id(self) -> str:
        return f"run-{uuid4().hex}"

    def now(self) -> datetime:
        return datetime.now(UTC)

    def attempt(
        self, number: int, previous_attempt_id: str | None = None
    ) -> CollectionAttempt:
        return CollectionAttempt(f"attempt-{uuid4().hex}", number, previous_attempt_id)
