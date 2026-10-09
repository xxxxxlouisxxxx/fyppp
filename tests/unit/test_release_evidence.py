"""Source-field provenance, transactional release evidence and reader fixtures."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from geo_research.dashboard.data import load_snapshot
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.evidence import ApprovedEvidence
from geo_research.storage.releases import ReleaseRepository
from geo_research.storage.reviews import append_review, history
from tests.unit.test_releases import _seed_complete_gold


@pytest.fixture
def fixture(tmp_path):
    raw = tmp_path / "response.json"
    raw.write_text(json.dumps({
        "answer": "Original fixture answer — not a generated snippet.",
        "sources": [{"url": "https://example.org/evidence"}],
    }), encoding="utf-8")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE analytics.gold_llm_brand_visibility SET raw_file_hash=?", [digest],
        )
    record = ApprovedEvidence(
        "e1", "llm-metric-1", "obs-llm-1", "llm", raw, digest,
        "/answer", "answer", "fixture reviewer", datetime.now(UTC),
        "approved fixture field for display", "fixture-parser-1", "fixture-registry-1",
    )
    return database, record


def test_original_evidence_and_reviews_are_release_scoped(fixture, tmp_path):
    database, record = fixture
    url = replace(record, evidence_id="url-1", json_pointer="/sources/0/url",
                  evidence_kind="citation_url")
    repository = ReleaseRepository(database)
    repository.complete("r1", evidence=(record, url))
    repository.complete("r2")
    before = hashlib.sha256(database.path.read_bytes()).hexdigest()
    snapshot = load_snapshot(database.path, "r1")
    assert snapshot.message is None
    assert set(snapshot.evidence.release_id) == {"r1"}
    assert snapshot.evidence.original_text.dropna().tolist() == [
        "Original fixture answer — not a generated snippet.",
    ]
    assert snapshot.evidence.url.dropna().tolist() == ["https://example.org/evidence"]
    assert load_snapshot(database.path).evidence.empty
    store = tmp_path / "reviews.sqlite"
    append_review(
        store, database.path, opportunity_id="h1", release_id="r1",
        expected_sequence=0, status="new", classification="hypothesis",
        reviewer="reviewer", reason="review original source", evidence=("e1", "url-1"),
    )
    assert history(store)[0]["release_id"] == "r1"
    assert hashlib.sha256(database.path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("changes", [
    {"raw_file_hash": "bad"}, {"metric_id": "not-a-metric"},
    {"observation_id": "other-observation"}, {"json_pointer": "/absent"},
    {"json_pointer": "/sources"}, {"reviewer": ""},
    {"quality_status": "validated"}, {"approved_at": datetime(2026, 10, 8)},
    {"evidence_kind": "citation_url"},
])
def test_invalid_evidence_rolls_back_entire_release(fixture, changes):
    database, record = fixture
    repository = ReleaseRepository(database)
    repository.complete("prior")
    with pytest.raises(ValueError):
        repository.complete("rejected", evidence=(replace(record, **changes),))
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) FROM presentation.releases WHERE release_id='rejected'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT release_id FROM presentation.release_current"
        ).fetchone()[0] == "prior"
        assert connection.execute(
            "SELECT count(*) FROM presentation.release_evidence"
        ).fetchone()[0] == 0