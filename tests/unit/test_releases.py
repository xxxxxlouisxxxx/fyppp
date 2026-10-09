from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from geo_research.cli import main
from geo_research.exceptions import ReleaseImmutableError, ReleaseIncompleteError
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.releases import ReleaseRepository


def _seed_complete_gold(database: DuckDBStore) -> None:
    with database.transaction() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO bronze.comparison_registry "
            "VALUES ('comparison-001', 'query-001', 'prompt-001', true, "
            "timestamp '2026-09-25 09:50:00+00')"
        )
        connection.execute("CREATE SCHEMA IF NOT EXISTS analytics")
        connection.execute(
            """
            CREATE TABLE analytics.gold_serp_brand_visibility (
                metric_id VARCHAR,
                observation_id VARCHAR,
                query_id VARCHAR,
                brand_id VARCHAR,
                brand_canonical_name VARCHAR,
                provider VARCHAR,
                search_engine VARCHAR,
                search_type VARCHAR,
                collection_window VARCHAR,
                source_category VARCHAR,
                metric_name VARCHAR,
                metric_version VARCHAR,
                numerator BIGINT,
                denominator BIGINT,
                metric_value DOUBLE,
                availability_status VARCHAR,
                collection_status VARCHAR,
                has_results BOOLEAN,
                best_normalized_rank INTEGER,
                response_id VARCHAR,
                raw_file_hash VARCHAR,
                language_code VARCHAR,
                location_code VARCHAR,
                raw_language_code VARCHAR,
                raw_location_code VARCHAR,
                device VARCHAR,
                collected_at TIMESTAMPTZ
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE analytics.gold_llm_brand_visibility (
                metric_id VARCHAR,
                observation_id VARCHAR,
                prompt_id VARCHAR,
                brand_id VARCHAR,
                brand_canonical_name VARCHAR,
                provider VARCHAR,
                platform VARCHAR,
                model_name VARCHAR,
                source_category VARCHAR,
                metric_name VARCHAR,
                metric_version VARCHAR,
                numerator BIGINT,
                denominator BIGINT,
                metric_value DOUBLE,
                availability_status VARCHAR,
                collection_status VARCHAR,
                mention_count BIGINT,
                citation_count BIGINT,
                request_id VARCHAR,
                response_id VARCHAR,
                raw_file_hash VARCHAR,
                language_code VARCHAR,
                location_code VARCHAR,
                raw_language_code VARCHAR,
                raw_location_code VARCHAR,
                collection_window VARCHAR,
                collected_at TIMESTAMPTZ
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE analytics.gold_comparison_brand_metrics (
                metric_id VARCHAR,
                comparison_id VARCHAR,
                query_id VARCHAR,
                prompt_id VARCHAR,
                brand_id VARCHAR,
                brand_canonical_name VARCHAR,
                metric_name VARCHAR,
                metric_version VARCHAR,
                serp_observation_id VARCHAR,
                llm_observation_id VARCHAR,
                serp_availability_status VARCHAR,
                llm_availability_status VARCHAR,
                serp_collection_status VARCHAR,
                llm_collection_status VARCHAR,
                serp_numerator BIGINT,
                serp_denominator BIGINT,
                serp_metric_value DOUBLE,
                llm_numerator BIGINT,
                llm_denominator BIGINT,
                llm_metric_value DOUBLE,
                metric_value DOUBLE,
                availability_status VARCHAR,
                language_code VARCHAR,
                location_code VARCHAR,
                serp_provider VARCHAR,
                search_engine VARCHAR,
                search_type VARCHAR,
                device VARCHAR,
                llm_provider VARCHAR,
                platform VARCHAR,
                model_name VARCHAR,
                collection_window VARCHAR,
                serp_collected_at TIMESTAMPTZ,
                llm_collected_at TIMESTAMPTZ,
                comparison_eligibility VARCHAR
            )
            """
        )
        connection.execute(
            """
            INSERT INTO analytics.gold_serp_brand_visibility VALUES (
                'serp-metric-1', 'obs-serp-1', 'query-001', 'brand-001',
                'Example', 'dataforseo', 'google', 'organic', '2026-09-25',
                'serp', 'serp_organic_sov', '1.0.0', 1, 1, 1.0, 'available',
                'available', true, 1, 'response-1', 'hash-1',
                'zh-TW', '2344', 'zh_TW', '2344', 'mobile',
                TIMESTAMPTZ '2026-09-25 09:51:02+00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO analytics.gold_llm_brand_visibility VALUES (
                'llm-metric-1', 'obs-llm-1', 'prompt-001', 'brand-001',
                'Example', 'dataforseo', 'chatgpt', 'gpt-4o', 'llm',
                'llm_brand_mention', '1.0.0', 1, 1, 1.0, 'available',
                'available', 1, 1, 'request-llm-1', 'response-llm-1', 'hash-llm-1',
                'zh-TW', '2344', 'zh_TW', '2344', '2026-09-25',
                TIMESTAMPTZ '2026-09-25 09:52:03+00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO analytics.gold_comparison_brand_metrics VALUES (
                'cmp-metric-1', 'comparison-001', 'query-001', 'prompt-001',
                'brand-001', 'Example', 'comparison_brand_visibility', '1.0.0',
                'obs-serp-1', 'obs-llm-1', 'available', 'available',
                'available', 'available', 1, 1, 1.0, 1, 1, 1.0, 0.0, 'available',
                'zh-TW', '2344', 'dataforseo', 'google', 'organic', 'mobile',
                'dataforseo', 'chatgpt', 'gpt-4o', '2026-09-25',
                TIMESTAMPTZ '2026-09-25 09:51:02+00',
                TIMESTAMPTZ '2026-09-25 09:52:03+00', 'eligible'
            )
            """
        )


def test_incomplete_release_is_rejected_and_not_current(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    repository = ReleaseRepository(database)

    report = repository.assess()
    with pytest.raises(ReleaseIncompleteError):
        repository.complete("release-incomplete")

    assert report.complete is False
    assert repository.current_release_id() is None
    with database.transaction() as connection:
        status = connection.execute(
            "SELECT status FROM presentation.releases WHERE release_id = ?",
            ["release-incomplete"],
        ).fetchone()[0]
        current_count = connection.execute(
            "SELECT count(*) FROM presentation.release_current"
        ).fetchone()[0]
    assert status == "incomplete"
    assert current_count == 0


def test_completed_release_snapshots_gold_and_sets_current(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    repository = ReleaseRepository(database)

    report = repository.complete("release-001", notes="phase-d fixture")

    assert report.complete is True
    assert repository.current_release_id() == "release-001"
    with database.transaction() as connection:
        serp_count = connection.execute(
            "SELECT count(*) FROM presentation.release_serp_brand_visibility "
            "WHERE release_id = 'release-001'"
        ).fetchone()[0]
        llm_count = connection.execute(
            "SELECT count(*) FROM presentation.release_llm_brand_visibility "
            "WHERE release_id = 'release-001'"
        ).fetchone()[0]
        comparison_count = connection.execute(
            "SELECT count(*) FROM presentation.release_comparison_brand_metrics "
            "WHERE release_id = 'release-001'"
        ).fetchone()[0]
        status, notes = connection.execute(
            "SELECT status, notes FROM presentation.releases "
            "WHERE release_id = 'release-001'"
        ).fetchone()
    assert (serp_count, llm_count, comparison_count) == (1, 1, 1)
    assert status == "completed"
    assert notes == "phase-d fixture"


@pytest.mark.parametrize("invalidate_gold", [False, True])
def test_completed_id_cannot_be_overwritten(tmp_path, invalidate_gold):
    database = DuckDBStore(tmp_path / "immutable.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    repository = ReleaseRepository(database)
    repository.complete("first", notes="original")
    repository.complete("second")
    with database.transaction() as connection:
        if invalidate_gold:
            connection.execute("DROP TABLE analytics.gold_serp_brand_visibility")
        else:
            connection.execute(
                "UPDATE analytics.gold_serp_brand_visibility SET numerator=0"
            )
    before = hashlib.sha256(database.path.read_bytes()).hexdigest()
    with pytest.raises(ReleaseImmutableError, match="immutable"):
        repository.complete("first", notes="replacement")
    assert hashlib.sha256(database.path.read_bytes()).hexdigest() == before
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT release_id FROM presentation.release_current"
        ).fetchone()[0] == "second"
        assert connection.execute(
            "SELECT notes FROM presentation.releases WHERE release_id='first'"
        ).fetchone()[0] == "original"
        assert connection.execute(
            "SELECT numerator FROM presentation.release_serp_brand_visibility "
            "WHERE release_id='first'"
        ).fetchone()[0] == 1


def test_snapshot_failure_rolls_back_publication(tmp_path, monkeypatch):
    database = DuckDBStore(tmp_path / "atomic.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    repository = ReleaseRepository(database)
    repository.complete("prior")

    def fail(connection, release_id, report):
        connection.execute(
            "DELETE FROM presentation.release_serp_brand_visibility"
        )
        raise RuntimeError("simulated snapshot failure")

    monkeypatch.setattr(repository, "_publish", fail)
    with pytest.raises(RuntimeError, match="snapshot failure"):
        repository.complete("failed")
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) FROM presentation.releases WHERE release_id='failed'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT release_id FROM presentation.release_current"
        ).fetchone()[0] == "prior"
        assert connection.execute(
            "SELECT count(*) FROM presentation.release_serp_brand_visibility"
        ).fetchone()[0] == 1


def test_publication_preserves_locale_context_and_provider_receive_times(
    tmp_path: Path,
) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    repository = ReleaseRepository(database)

    repository.complete("release-locale")

    serp_received_at = datetime(2026, 9, 25, 9, 51, 2, tzinfo=UTC)
    llm_received_at = datetime(2026, 9, 25, 9, 52, 3, tzinfo=UTC)
    with database.transaction() as connection:
        serp = connection.execute(
            "SELECT language_code, location_code, raw_language_code, "
            "raw_location_code, device, collected_at "
            "FROM presentation.release_serp_brand_visibility"
        ).fetchone()
        llm = connection.execute(
            "SELECT language_code, location_code, raw_language_code, "
            "raw_location_code, collection_window, collected_at "
            "FROM presentation.release_llm_brand_visibility"
        ).fetchone()
        comparison = connection.execute(
            "SELECT language_code, location_code, serp_provider, search_engine, "
            "search_type, device, llm_provider, platform, model_name, "
            "collection_window, serp_collected_at, llm_collected_at, "
            "comparison_eligibility "
            "FROM presentation.release_comparison_brand_metrics"
        ).fetchone()
    assert serp == ("zh-TW", "2344", "zh_TW", "2344", "mobile", serp_received_at)
    assert llm == ("zh-TW", "2344", "zh_TW", "2344", "2026-09-25", llm_received_at)
    assert comparison == (
        "zh-TW", "2344", "dataforseo", "google", "organic", "mobile",
        "dataforseo", "chatgpt", "gpt-4o", "2026-09-25",
        serp_received_at, llm_received_at, "eligible",
    )


@pytest.mark.parametrize(
    ("relation", "column"),
    [
        ("gold_serp_brand_visibility", "language_code"),
        ("gold_llm_brand_visibility", "collected_at"),
        ("gold_comparison_brand_metrics", "comparison_eligibility"),
    ],
)
def test_missing_gold_context_column_blocks_publication(
    tmp_path: Path, relation: str, column: str,
) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    with database.transaction() as connection:
        connection.execute(f"ALTER TABLE analytics.{relation} DROP COLUMN {column}")
    repository = ReleaseRepository(database)

    with pytest.raises(
        ReleaseIncompleteError, match=f"missing_column:analytics.{relation}.{column}"
    ):
        repository.complete("release-missing-context")

    assert repository.current_release_id() is None
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) FROM presentation.release_serp_brand_visibility"
        ).fetchone()[0] == 0


def test_unknown_gold_context_remains_null_in_snapshot(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    with database.transaction() as connection:
        for relation in ("serp", "llm"):
            connection.execute(
                f"UPDATE analytics.gold_{relation}_brand_visibility "
                "SET language_code = NULL, location_code = NULL, "
                "raw_language_code = NULL, raw_location_code = NULL, "
                "collected_at = NULL"
            )
        connection.execute(
            "UPDATE analytics.gold_comparison_brand_metrics "
            "SET language_code = NULL, location_code = NULL, "
            "serp_collected_at = NULL, llm_collected_at = NULL, "
            "comparison_eligibility = 'unknown_locale'"
        )
    ReleaseRepository(database).complete("release-unknown-context")

    with database.transaction() as connection:
        for relation in ("serp", "llm"):
            assert connection.execute(
                "SELECT language_code, location_code, raw_language_code, "
                "raw_location_code, collected_at "
                f"FROM presentation.release_{relation}_brand_visibility"
            ).fetchone() == (None,) * 5
        assert connection.execute(
            "SELECT language_code, location_code, serp_collected_at, "
            "llm_collected_at, comparison_eligibility "
            "FROM presentation.release_comparison_brand_metrics"
        ).fetchone() == (None, None, None, None, "unknown_locale")


def test_unavailable_gold_metric_value_blocks_completion(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    _seed_complete_gold(database)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE analytics.gold_serp_brand_visibility "
            "SET availability_status = 'not_collected', metric_value = 0.0"
        )
    repository = ReleaseRepository(database)

    with pytest.raises(
        ReleaseIncompleteError, match="unavailable_metric_value_present"
    ):
        repository.complete("release-bad")
    assert repository.current_release_id() is None


def test_release_cli_complete_and_status(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "warehouse.duckdb"
    database = DuckDBStore(database_path)
    database.initialize()
    _seed_complete_gold(database)

    assert main(["release", "complete", "--database", str(database_path),
                 "--release-id", "release-cli"]) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["completed"] is True
    assert completed["current_release_id"] == "release-cli"

    assert main(["release", "status", "--database", str(database_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["complete"] is True
    assert status["current_release_id"] == "release-cli"


def test_release_cli_rejects_incomplete(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "warehouse.duckdb"
    DuckDBStore(database_path).initialize()

    assert main(["release", "complete", "--database", str(database_path),
                 "--release-id", "release-cli-bad"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["completed"] is False
    assert payload["reasons"]
