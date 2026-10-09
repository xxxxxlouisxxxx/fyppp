from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.raw_registration import register_verified_raw_evidence
from geo_research.storage.raw_store import RawEvidence, RawStore


def _evidence() -> RawEvidence:
    return RawEvidence(
        source_category="serp",
        provider="dataforseo",
        platform_or_engine="google",
        run_id="run-raw-registration",
        request_id="request-raw-registration",
        collected_at=datetime(2026, 10, 1, tzinfo=UTC),
        request_payload={"post": []},
        response_payload={"tasks": []},
    )


def test_registers_existing_verified_raw_artifacts_without_rewriting_files(
    tmp_path: Path,
) -> None:
    raw_store = RawStore(tmp_path / "raw")
    result = raw_store.write(_evidence())
    database = DuckDBStore(tmp_path / "warehouse.duckdb")

    report = register_verified_raw_evidence(database, raw_store.root)

    assert report.registered == 1
    assert report.already_registered == 0
    assert not report.invalid_directories
    assert result.response.path.is_file()
    with database.transaction() as connection:
        request_count = connection.execute(
            "SELECT count(*) FROM bronze.api_requests"
        ).fetchone()[0]
        raw_count = connection.execute(
            "SELECT count(*) FROM bronze.raw_files"
        ).fetchone()[0]
    assert (request_count, raw_count) == (1, 2)


def test_repeated_registration_leaves_existing_request_untouched(
    tmp_path: Path,
) -> None:
    raw_store = RawStore(tmp_path / "raw")
    raw_store.write(_evidence())
    database = DuckDBStore(tmp_path / "warehouse.duckdb")

    register_verified_raw_evidence(database, raw_store.root)
    report = register_verified_raw_evidence(database, raw_store.root)

    assert report.registered == 0
    assert report.already_registered == 1