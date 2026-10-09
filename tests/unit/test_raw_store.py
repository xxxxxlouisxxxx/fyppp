from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from geo_research.storage.raw_store import (
    RawEvidence,
    RawEvidenceConflictError,
    RawStore,
)


def evidence(category: str = "serp", platform: str = "google") -> RawEvidence:
    return RawEvidence(
        source_category=category,
        provider="dataforseo",
        platform_or_engine=platform,
        run_id="run-1",
        request_id="request-1",
        collected_at=datetime(2026, 9, 25, tzinfo=UTC),
        request_payload={"keyword": "example", "Authorization": "Basic unsafe"},
        response_payload={"tasks": [{"result": "complete"}]},
        request_content_type="application/json",
        response_content_type="application/json",
    )


def test_successful_write_is_immutable_sanitized_and_integrity_checked(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path)

    result = store.write(evidence())

    assert (
        result.directory
        == tmp_path
        / "serp"
        / "dataforseo"
        / "google"
        / "2026"
        / "09"
        / "25"
        / "run-1"
        / "request-1"
    )
    request_text = (result.directory / "request.json").read_text(encoding="utf-8")
    assert "unsafe" not in request_text
    assert "Authorization" not in request_text
    response_text = (result.directory / "response.json").read_text(encoding="utf-8")
    assert response_text.count("complete") == 1
    assert response_text.startswith('{\n  "tasks": [\n')
    assert store.verify(result.directory).valid is True


def test_repeated_identical_write_is_idempotent_and_conflict_does_not_overwrite(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path)
    original = store.write(evidence())

    assert store.write(evidence()) == original
    changed = evidence()
    changed.response_payload["tasks"] = [{"result": "different"}]
    with pytest.raises(RawEvidenceConflictError):
        store.write(changed)

    assert "complete" in (original.directory / "response.json").read_text(
        encoding="utf-8"
    )


def test_orphans_checksum_mismatch_and_serp_llm_path_isolation(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    serp = store.write(evidence())
    llm = store.write(evidence("llm", "chatgpt"))
    (serp.directory / "response.json").write_text("{}", encoding="utf-8")
    orphan = (
        tmp_path
        / "serp"
        / "dataforseo"
        / "bing"
        / "2026"
        / "09"
        / "25"
        / "run-2"
        / "request-2"
    )
    orphan.mkdir(parents=True)
    (orphan / "response.json.tmp").write_text("partial", encoding="utf-8")

    assert serp.directory != llm.directory
    assert store.verify(serp.directory).valid is False
    assert orphan in store.find_orphans()


def test_two_writers_same_path_do_not_overwrite(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.write(evidence())
    conflicting = evidence()
    conflicting.request_payload["keyword"] = "changed"

    with pytest.raises(RawEvidenceConflictError):
        store.write(conflicting)
