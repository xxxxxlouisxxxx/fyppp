from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from geo_research.parsers.serp.features import parse_serp_features
from geo_research.parsers.serp.service import SERPParseInput, parse_serp_response
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.migrations import MIGRATION_006, MIGRATION_007
from geo_research.storage.raw_store import RawEvidence, RawStore
from geo_research.storage.releases import ReleaseRepository
from geo_research.storage.repositories import (
    RawEvidenceRepository,
    SilverSERPFeatureRepository,
    SilverSERPRepository,
)


def raw_evidence() -> RawEvidence:
    return RawEvidence(
        source_category="serp",
        provider="dataforseo",
        platform_or_engine="google",
        run_id="run-1",
        request_id="request-1",
        collected_at=datetime(2026, 9, 25, tzinfo=UTC),
        request_payload={"keyword": "example"},
        response_payload={"tasks": []},
        request_content_type="application/json",
        response_content_type="application/json",
    )


def test_response_saved_before_db_commit_is_detectable(tmp_path: Path) -> None:
    raw = RawStore(tmp_path / "raw")
    result = raw.write(raw_evidence())
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()

    report = RawEvidenceRepository(database, raw).verify()

    assert result.directory in report.unreferenced_raw_directories


def test_db_row_with_missing_raw_file_is_detectable(tmp_path: Path) -> None:
    raw = RawStore(tmp_path / "raw")
    result = raw.write(raw_evidence())
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    repository = RawEvidenceRepository(database, raw)
    repository.record(raw_evidence(), result)
    for path in result.directory.iterdir():
        path.unlink()
    result.directory.rmdir()

    report = repository.verify()

    assert str(result.directory) in report.missing_raw_directories


def test_serp_parse_output_is_traceably_persisted_to_silver(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    parsed = parse_serp_response(
        SERPParseInput(
            query_id="query-1",
            provider="dataforseo",
            search_engine="google",
            search_type="organic",
            location_code="2840",
            language_code="en",
            device="desktop",
            collection_window="2026-09-25",
            response_id="response-1",
            source_ingestion_id="run-1",
            raw_file_hash="raw-hash-1",
            response_payload={
                "tasks": [
                    {
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "unknown_type",
                                        "rank_absolute": 1,
                                        "url": "https://example.test",
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
        )
    )

    SilverSERPRepository(database).record(parsed)

    with database.transaction() as connection:
        observation_count = connection.execute(
            "SELECT count(*) FROM silver.silver_search_observations"
        ).fetchone()[0]
        item_row = connection.execute(
            "SELECT observation_id, raw_file_hash FROM silver.silver_serp_items"
        ).fetchone()
        quarantine_count = connection.execute(
            "SELECT count(*) FROM silver.silver_serp_parsing_quarantine"
        ).fetchone()[0]
    assert observation_count == 1
    assert item_row == (parsed.observation.observation_id, "raw-hash-1")
    assert quarantine_count == 1


def test_serp_feature_output_preserves_parent_and_raw_evidence(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    parsed = parse_serp_response(
        SERPParseInput(
            query_id="query-1",
            provider="dataforseo",
            search_engine="google",
            search_type="organic",
            location_code="2840",
            language_code="en",
            device="desktop",
            collection_window="2026-09-25",
            response_id="response-1",
            source_ingestion_id="run-1",
            raw_file_hash="raw-hash-1",
            response_payload={
                "tasks": [
                    {
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "organic",
                                        "rank_absolute": 1,
                                        "url": "https://example.test",
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
        )
    )
    SilverSERPRepository(database).record(parsed)

    SilverSERPFeatureRepository(database).record(parse_serp_features(parsed))

    with database.transaction() as connection:
        row = connection.execute(
            "SELECT observation_id, parent_serp_item_id, raw_evidence "
            "FROM silver.silver_organic_results"
        ).fetchone()
    assert row == (
        parsed.observation.observation_id,
        parsed.items[0].serp_item_id,
        parsed.items[0].raw_item_json,
    )


def test_all_phase9_feature_tables_are_created(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()

    with database.transaction() as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'silver'"
            ).fetchall()
        }

    assert {
        "silver_organic_results",
        "silver_paid_results",
        "silver_local_results",
        "silver_question_results",
        "silver_related_queries",
        "silver_image_results",
        "silver_llm_observations",
    } <= table_names


def test_presentation_release_tables_are_created(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()

    with database.transaction() as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'presentation'"
            ).fetchall()
        }
        migration_ids = {
            row[0]
            for row in connection.execute(
                "SELECT migration_id FROM meta.schema_migrations"
            ).fetchall()
        }

    assert {
        "releases",
        "release_current",
        "release_serp_brand_visibility",
        "release_llm_brand_visibility",
        "release_comparison_brand_metrics",
    } <= table_names
    assert "006_presentation_releases" in migration_ids


def test_release_context_migration_preserves_legacy_snapshots(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "legacy.duckdb")
    database.initialize()
    tables = {
        "release_serp_brand_visibility": (
            "language_code", "location_code", "raw_language_code", "raw_location_code",
            "device", "collected_at",
        ),
        "release_llm_brand_visibility": (
            "language_code", "location_code", "raw_language_code", "raw_location_code",
            "collection_window", "collected_at",
        ),
        "release_comparison_brand_metrics": (
            "language_code", "location_code", "serp_provider", "search_engine",
            "search_type", "device", "llm_provider", "platform", "model_name",
            "collection_window", "serp_collected_at", "llm_collected_at",
            "comparison_eligibility",
        ),
    }
    with database.transaction() as connection:
        # Recreate the exact pre-upgrade schema even if initialization later learns 007.
        for table in tables:
            connection.execute(f"DROP TABLE presentation.{table}")
        connection.execute(MIGRATION_006)
        for table in tables:
            columns = connection.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'presentation' AND table_name = ? "
                "ORDER BY ordinal_position",
                [table],
            ).fetchall()
            values = [
                "legacy-release" if name == "release_id"
                else "legacy-metric" if name == "metric_id"
                else "legacy" if data_type == "VARCHAR"
                else True if data_type == "BOOLEAN"
                else 1
                for name, data_type in columns
            ]
            connection.execute(
                f"INSERT INTO presentation.{table} "
                f"({', '.join(name for name, _ in columns)}) "
                f"VALUES ({', '.join('?' for _ in values)})",
                values,
            )
        before = {
            table: connection.execute(f"SELECT * FROM presentation.{table}").fetchone()
            for table in tables
        }
        connection.execute(MIGRATION_007)
        connection.execute(MIGRATION_007)

    # Exercise the production release-boundary upgrade and migration ledger too.
    ReleaseRepository(database).assess()
    with database.transaction() as connection:
        for table, new_columns in tables.items():
            row = connection.execute(f"SELECT * FROM presentation.{table}").fetchone()
            assert row == before[table] + (None,) * len(new_columns)
            columns = connection.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'presentation' AND table_name = ? "
                "ORDER BY ordinal_position",
                [table],
            ).fetchall()[-len(new_columns):]
            assert [name for name, _, _ in columns] == list(new_columns)
            assert all(nullable == "YES" for _, _, nullable in columns)
            assert all(
                data_type == (
                    "TIMESTAMP WITH TIME ZONE" if name.endswith("collected_at")
                    else "VARCHAR"
                )
                for name, data_type, _ in columns
            )
        assert connection.execute(
            "SELECT count(*) FROM meta.schema_migrations "
            "WHERE migration_id = '007_release_collection_context'"
        ).fetchone()[0] == 1
