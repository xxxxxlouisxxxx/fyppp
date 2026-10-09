"""Local DuckDB connection and migration boundary."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from geo_research.storage.evidence import EVIDENCE_SCHEMA
from geo_research.storage.migrations import (
    MIGRATION_001,
    MIGRATION_002,
    MIGRATION_003,
    MIGRATION_004,
    MIGRATION_005,
    MIGRATION_006,
    MIGRATION_007,
    MIGRATION_008,
    MIGRATION_009,
)


class DuckDBStore:
    """Owns explicit DuckDB schema initialization and transactions."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create schemas/tables in a single migration transaction."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.path)) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                for migration_id, migration in (
                    ("001_bronze_metadata", MIGRATION_001),
                    ("002_silver_serp_parsing", MIGRATION_002),
                    ("003_silver_serp_features", MIGRATION_003),
                    ("004_bronze_collection_context", MIGRATION_004),
                    ("005_silver_llm_observations", MIGRATION_005),
                    ("006_presentation_releases", MIGRATION_006),
                    ("007_release_collection_context", MIGRATION_007),
                    ("008_silver_response_evidence", MIGRATION_008),
                    ("009_readable_feature_evidence_v2", MIGRATION_009),
                    ("010_approved_release_evidence", EVIDENCE_SCHEMA),
                ):
                    connection.execute(migration)
                    connection.execute(
                        "INSERT OR IGNORE INTO meta.schema_migrations "
                        "VALUES (?, current_timestamp)",
                        [migration_id],
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    @contextmanager
    def transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Yield one explicit metadata transaction; callers commit as a unit."""
        connection = duckdb.connect(str(self.path))
        connection.execute("BEGIN TRANSACTION")
        try:
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def fetch_raw_directories(self) -> set[str]:
        """Return directories referenced by committed raw-file metadata."""
        if not self.path.exists():
            return set()
        with duckdb.connect(str(self.path), read_only=True) as connection:
            rows = connection.execute(
                "SELECT DISTINCT raw_directory FROM bronze.raw_files"
            ).fetchall()
        return {str(row[0]) for row in rows}
