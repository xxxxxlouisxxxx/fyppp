"""Review fixtures are isolated from production data and registry approval."""

import hashlib
import sqlite3

import pytest

from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.releases import ReleaseRepository
from geo_research.storage.reviews import append_review, history, main
from tests.unit.test_releases import _seed_complete_gold


@pytest.fixture
def fixture(tmp_path):
    warehouse = tmp_path / "snapshots.duckdb"
    database = DuckDBStore(warehouse)
    database.initialize()
    _seed_complete_gold(database)
    ReleaseRepository(database).complete("r1")
    store = tmp_path / "reviews.sqlite"
    args = dict(
        opportunity_id="hypothesis-1", release_id="r1", expected_sequence=0,
        status="new", classification="hypothesis", reviewer="manual reviewer",
        reason="investigate observed mismatch", evidence=("cmp-metric-1",),
    )
    return store, warehouse, args


def test_reviews_actions_and_classification_are_separate(fixture):
    store, warehouse, args = fixture
    before = hashlib.sha256(warehouse.read_bytes()).hexdigest()
    append_review(store, warehouse, **args)
    append_review(store, warehouse, **{
        **args, "expected_sequence": 1, "status": "in_review",
    })
    append_review(store, warehouse, **{
        **args, "expected_sequence": 2, "status": "action_planned",
        "next_action": "review original evidence before planning experiment",
        "counter_evidence": ("serp-metric-1",),
    })
    events = history(store, "hypothesis-1")
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert {event["classification"] for event in events} == {"hypothesis"}
    assert events[-1]["next_action"]
    assert events[-1]["previous_status"] == "in_review"
    assert hashlib.sha256(warehouse.read_bytes()).hexdigest() == before
    with sqlite3.connect(store) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM review_events")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE review_events SET reason='rewritten'")


@pytest.mark.parametrize("changes", [
    {"reviewer": " "}, {"reason": ""}, {"evidence": ()},
    {"evidence": ("not-in-release",)}, {"counter_evidence": ("missing",)},
    {"release_id": "draft"}, {"status": "closed"},
    {"classification": "validated_opportunity"}, {"expected_sequence": 1},
])
def test_invalid_review_is_rejected(fixture, changes):
    store, warehouse, args = fixture
    with pytest.raises(ValueError):
        append_review(store, warehouse, **{**args, **changes})
    assert not store.exists() or history(store) == []


def test_stale_writer_and_action_validation(fixture):
    store, warehouse, args = fixture
    append_review(store, warehouse, **args)
    with pytest.raises(ValueError, match="stale"):
        append_review(store, warehouse, **args)
    with pytest.raises(ValueError, match="actionable"):
        append_review(store, warehouse, **{
            **args, "expected_sequence": 1, "status": "action_planned",
        })
    with pytest.raises(ValueError, match="transition"):
        append_review(store, warehouse, **{
            **args, "expected_sequence": 1, "status": "experiment_running",
            "next_action": "test",
        })
    with pytest.raises(ValueError, match="separate"):
        append_review(warehouse, warehouse, **args)


def test_reader_never_creates_or_changes_store(fixture, tmp_path):
    missing = tmp_path / "missing.sqlite"
    assert history(missing) == [] and not missing.exists()
    store, warehouse, args = fixture
    append_review(store, warehouse, **args)
    before = hashlib.sha256(store.read_bytes()).hexdigest()
    assert history(store)
    assert hashlib.sha256(store.read_bytes()).hexdigest() == before
    assert main(["--store", str(store), "history"]) == 0


def test_archived_opportunity_is_terminal(fixture):
    store, warehouse, args = fixture
    append_review(store, warehouse, **args)
    append_review(store, warehouse, **{
        **args, "expected_sequence": 1, "status": "archived",
    })
    with pytest.raises(ValueError, match="archived"):
        append_review(store, warehouse, **{
            **args, "expected_sequence": 2, "status": "archived",
            "classification": "interpretation",
        })
    assert len(history(store)) == 2