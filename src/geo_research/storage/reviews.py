"""Local controlled review writer; analytical release snapshots stay read-only.

No registry promotion or commercial-validation classification is supported here.
Evidence references are existing metric IDs in a completed immutable release.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import duckdb

STATES = {
    "new": {"in_review", "archived"},
    "in_review": {"needs_evidence", "action_planned", "closed", "archived"},
    "needs_evidence": {"in_review", "action_planned", "archived"},
    "action_planned": {"in_review", "experiment_running", "closed", "archived"},
    "experiment_running": {"needs_evidence", "closed", "archived"},
    "closed": {"in_review", "archived"},
    "archived": set(),
}
CLASSES = {"observation", "interpretation", "hypothesis"}
TABLES = (
    "release_serp_brand_visibility",
    "release_llm_brand_visibility",
    "release_comparison_brand_metrics",
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS review_events (
 event_id TEXT PRIMARY KEY,
 opportunity_id TEXT NOT NULL,
 release_id TEXT NOT NULL,
 sequence INTEGER NOT NULL,
 previous_status TEXT,
 status TEXT NOT NULL,
 classification TEXT NOT NULL,
 reviewer TEXT NOT NULL,
 recorded_at TEXT NOT NULL,
 reason TEXT NOT NULL,
 evidence_json TEXT NOT NULL,
 counter_evidence_json TEXT NOT NULL,
 next_action TEXT NOT NULL,
 UNIQUE(opportunity_id, sequence)
);
CREATE TRIGGER IF NOT EXISTS no_review_updates
BEFORE UPDATE ON review_events BEGIN
 SELECT RAISE(ABORT, 'review events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_review_deletes
BEFORE DELETE ON review_events BEGIN
 SELECT RAISE(ABORT, 'review events are append-only'); END;
"""


def history(path: Path, opportunity_id: str | None = None) -> list[dict[str, object]]:
    """Read existing review events without creating a store or initializing it."""
    if not path.is_file():
        return []
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        query = "SELECT * FROM review_events"
        args: tuple[str, ...] = ()
        if opportunity_id is not None:
            query += " WHERE opportunity_id=?"
            args = (opportunity_id,)
        query += " ORDER BY opportunity_id, sequence"
        return [dict(row) for row in connection.execute(query, args)]


def _validate_evidence(
    warehouse: Path, release_id: str, references: tuple[str, ...],
) -> None:
    if not warehouse.is_file():
        raise ValueError("analytical warehouse does not exist")
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        connection.execute("BEGIN TRANSACTION")
        row = connection.execute(
            "SELECT status FROM presentation.releases WHERE release_id=?", [release_id],
        ).fetchone()
        if not row or row[0] != "completed":
            raise ValueError("review requires a completed release")
        for reference in references:
            found = any(
                connection.execute(
                    f"SELECT count(*) FROM presentation.{table} "
                    "WHERE release_id=? AND metric_id=?", [release_id, reference],
                ).fetchone()[0]
                for table in TABLES
            )
            has_evidence = connection.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='presentation' AND table_name='release_evidence'"
            ).fetchone()[0]
            if not found and has_evidence:
                found = bool(connection.execute(
                    "SELECT count(*) FROM presentation.release_evidence "
                    "WHERE release_id=? AND evidence_id=?", [release_id, reference],
                ).fetchone()[0])
            has_research = connection.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='presentation' "
                "AND table_name='release_research_rows'"
            ).fetchone()[0]
            if not found and has_research:
                found = bool(connection.execute(
                    "SELECT count(*) FROM presentation.release_research_rows "
                    "WHERE release_id=? AND (row_id=? "
                    "OR json_extract_string(payload_json, '$.metric_id')=? "
                    "OR json_extract_string(payload_json, '$.evidence_id')=?)",
                    [release_id, reference, reference, reference],
                ).fetchone()[0])
            if not found:
                raise ValueError(f"evidence does not belong to release: {reference}")
        connection.execute("COMMIT")


def append_review(
    path: Path,
    warehouse: Path,
    *,
    opportunity_id: str,
    release_id: str,
    expected_sequence: int,
    status: str,
    classification: str,
    reviewer: str,
    reason: str,
    evidence: tuple[str, ...],
    counter_evidence: tuple[str, ...] = (),
    next_action: str = "",
) -> str:
    """Append a manually requested event after reference and concurrency checks."""
    if path.resolve() == warehouse.resolve():
        raise ValueError("review store must be separate from analytical warehouse")
    if path.suffix.lower() not in {".sqlite", ".sqlite3"}:
        raise ValueError("review store requires a dedicated .sqlite or .sqlite3 path")
    required = (opportunity_id, release_id, reviewer, reason)
    if any(not value.strip() for value in required):
        raise ValueError("opportunity, release, reviewer and reason are required")
    if status not in STATES or classification not in CLASSES:
        raise ValueError("unsupported workflow or evidence classification")
    references = (*evidence, *counter_evidence)
    if not evidence or any(not reference.strip() for reference in references):
        raise ValueError("nonblank release-scoped evidence references are required")
    if status in {"action_planned", "experiment_running"} and not next_action.strip():
        raise ValueError("an actionable next step is required")
    _validate_evidence(warehouse, release_id, (*evidence, *counter_evidence))
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            "SELECT sequence,status,release_id,classification FROM review_events "
            "WHERE opportunity_id=? ORDER BY sequence DESC LIMIT 1", [opportunity_id],
        ).fetchone()
        sequence = previous[0] if previous else 0
        if sequence != expected_sequence:
            raise ValueError("stale review sequence; reload history")
        if previous:
            if previous[2] != release_id:
                raise ValueError("opportunity release identity cannot change")
            if previous[1] == "archived":
                raise ValueError("archived opportunity cannot receive new events")
            if status != previous[1] and status not in STATES[previous[1]]:
                raise ValueError("invalid workflow transition")
        elif status != "new":
            raise ValueError("first event must use new status")
        event_id = str(uuid4())
        connection.execute(
            "INSERT INTO review_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [event_id, opportunity_id, release_id, sequence + 1,
             previous[1] if previous else None, status, classification, reviewer,
             datetime.now(UTC).isoformat(), reason,
             json.dumps(sorted(set(evidence))),
             json.dumps(sorted(set(counter_evidence))),
             next_action],
        )
        return event_id


def main(argv: list[str] | None = None) -> int:
    """Explicit local action interface; never invoked by the snapshot dashboard."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("history")
    listing.add_argument("--opportunity-id")
    append = commands.add_parser("append")
    append.add_argument("--warehouse", type=Path, required=True)
    for name in ("opportunity-id", "release-id", "reviewer", "reason"):
        append.add_argument(f"--{name}", required=True)
    append.add_argument("--expected-sequence", type=int, required=True)
    append.add_argument("--status", choices=STATES, required=True)
    append.add_argument("--classification", choices=sorted(CLASSES), required=True)
    append.add_argument("--evidence", action="append", required=True)
    append.add_argument("--counter-evidence", action="append", default=[])
    append.add_argument("--next-action", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "history":
            print(json.dumps(history(args.store, args.opportunity_id)))
        else:
            event = append_review(
                args.store, args.warehouse, opportunity_id=args.opportunity_id,
                release_id=args.release_id, expected_sequence=args.expected_sequence,
                status=args.status, classification=args.classification,
                reviewer=args.reviewer, reason=args.reason,
                evidence=tuple(args.evidence),
                counter_evidence=tuple(args.counter_evidence),
                next_action=args.next_action,
            )
            print(json.dumps({"event_id": event}))
        return 0
    except (ValueError, sqlite3.Error, duckdb.Error) as error:
        print(json.dumps({"error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())