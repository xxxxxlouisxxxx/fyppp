"""Two fixture releases, evidence, action state and independent restore drill."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from geo_research.dashboard.data import load_snapshot
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.evidence import ApprovedEvidence
from geo_research.storage.recovery import backup, restore
from geo_research.storage.releases import ReleaseRepository
from geo_research.storage.reviews import append_review, history
from tests.unit.test_releases import _seed_complete_gold


def test_two_fixture_batches_and_independent_restore(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    database = DuckDBStore(root / "warehouse.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    raw = root / "raw.json"
    raw.write_text('{"answer":"original fixture answer"}', encoding="utf-8")
    raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE analytics.gold_llm_brand_visibility SET raw_file_hash=?",
            [raw_hash],
        )
    evidence = ApprovedEvidence(
        "original-answer", "llm-metric-1", "obs-llm-1", "llm", raw, raw_hash,
        "/answer", "answer", "fixture reviewer", datetime.now(UTC),
        "fixture display approval", "fixture-parser", "fixture-registry",
    )
    repository = ReleaseRepository(database)
    for index in (1, 2):
        release = f"fixture-batch-{index}"
        repository.complete(release, evidence=(evidence,))
        assert load_snapshot(database.path).release["release_id"] == release
        append_review(
            root / "reviews.sqlite", database.path, opportunity_id=f"h{index}",
            release_id=release, expected_sequence=0, status="new",
            classification="hypothesis", reviewer="fixture reviewer",
            reason="fixture investigation", evidence=("original-answer",),
        )
        for sequence, state in ((1, "in_review"), (2, "action_planned")):
            append_review(
                root / "reviews.sqlite", database.path, opportunity_id=f"h{index}",
                release_id=release, expected_sequence=sequence, status=state,
                classification="hypothesis", reviewer="fixture reviewer",
                reason="fixture manual review", evidence=("original-answer",),
                next_action="request independent evidence before experiment",
            )
    files = ("warehouse.duckdb", "reviews.sqlite", "raw.json")
    before = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
              for name in files}
    bundle = tmp_path / "backup"
    backup(root, bundle, files=files, reviewer="fixture reviewer",
           reason="independent recovery rehearsal", writers_stopped=True)
    destination = tmp_path / "restored"
    restore(bundle, destination)
    for name in files:
        restored_hash = hashlib.sha256((destination / name).read_bytes()).hexdigest()
        assert restored_hash == before[name]
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == before[name]
    assert load_snapshot(destination / "warehouse.duckdb").release["release_id"] == (
        "fixture-batch-2"
    )
    historical = load_snapshot(destination / "warehouse.duckdb", "fixture-batch-1")
    assert historical.message is None
    assert historical.evidence.original_text.tolist() == ["original fixture answer"]
    assert len(history(destination / "reviews.sqlite")) == 6
    with pytest.raises(ValueError, match="must not exist"):
        restore(bundle, root)


def test_recovery_requires_quiescence_and_safe_scope(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file").write_text("original", encoding="utf-8")
    kwargs = dict(files=("file",), reviewer="reviewer", reason="test")
    with pytest.raises(ValueError, match="stop all writers"):
        backup(source, tmp_path / "backup", **kwargs)
    with pytest.raises(ValueError, match="outside"):
        backup(source, source / "backup", **kwargs, writers_stopped=True)
    with pytest.raises(ValueError, match="relative"):
        backup(source, tmp_path / "backup", **{
            **kwargs, "files": ("../file",), "writers_stopped": True,
        })


def test_tampered_bundle_never_creates_restore_destination(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file").write_text("original", encoding="utf-8")
    bundle = tmp_path / "backup"
    backup(source, bundle, files=("file",), reviewer="reviewer", reason="test",
           writers_stopped=True)
    (bundle / "files/file").write_text("tampered", encoding="utf-8")
    destination = tmp_path / "restore"
    with pytest.raises(ValueError, match="checksum"):
        restore(bundle, destination)
    assert not destination.exists()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../escape"
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="relative"):
        restore(bundle, destination)