"""Completed-release completeness checks and presentation snapshots.

Presentation consumers may read only a completed current release. Incomplete
Gold output cannot be marked current and must not be treated as brand absence.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb

from geo_research.domain.comparisons import Comparison
from geo_research.exceptions import ReleaseImmutableError, ReleaseIncompleteError
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.evidence import ApprovedEvidence, publish_evidence
from geo_research.storage.research_snapshots import publish_research

_CURRENT_SLOT = "current"
_METRIC_VERSION = "1.0.0"
_REQUIRED_RELATIONS = (
    "analytics.gold_serp_brand_visibility",
    "analytics.gold_llm_brand_visibility",
    "analytics.gold_comparison_brand_metrics",
)
_REQUIRED_CONTEXT_COLUMNS = {
    _REQUIRED_RELATIONS[0]: (
        "language_code", "location_code", "raw_language_code", "raw_location_code",
        "device", "collected_at",
    ),
    _REQUIRED_RELATIONS[1]: (
        "language_code", "location_code", "raw_language_code", "raw_location_code",
        "collection_window", "collected_at",
    ),
    _REQUIRED_RELATIONS[2]: (
        "language_code", "location_code", "serp_provider", "search_engine",
        "search_type", "device", "llm_provider", "platform", "model_name",
        "collection_window", "serp_collected_at", "llm_collected_at",
        "comparison_eligibility",
    ),
}


@dataclass(frozen=True, slots=True)
class ReleaseCompletenessReport:
    """Machine-readable completeness result for one candidate release."""

    complete: bool
    reasons: tuple[str, ...]
    checks: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "reasons": list(self.reasons),
            "checks": self.checks,
        }


@dataclass(frozen=True, slots=True)
class ReleaseRecord:
    release_id: str
    status: str
    metric_version: str
    notes: str | None
    created_at: datetime | None
    completed_at: datetime | None


class ReleaseRepository:
    """Owns release completeness, snapshots, and the current-release pointer."""

    def __init__(self, database: DuckDBStore) -> None:
        self.database = database

    def _initialize(self) -> None:
        """Upgrade snapshots before use, including warehouses with old releases."""
        self.database.initialize()

    def assess(
        self, connection: duckdb.DuckDBPyConnection | None = None,
    ) -> ReleaseCompletenessReport:
        """Return whether Gold output is complete enough to publish."""
        if connection is None:
            self._initialize()
        reasons: list[str] = []
        checks: dict[str, Any] = {}
        context = (
            self.database.transaction()
            if connection is None else nullcontext(connection)
        )
        with context as connection:
            existing = {
                f"{schema}.{name}"
                for schema, name in connection.execute(
                    "SELECT table_schema, table_name "
                    "FROM information_schema.tables "
                    "WHERE table_schema IN ('analytics', 'bronze')"
                ).fetchall()
            }
            for relation in _REQUIRED_RELATIONS:
                present = relation in existing
                checks[f"{relation}_present"] = present
                if not present:
                    reasons.append(f"missing_relation:{relation}")
            # Require the source contract, but preserve unknown values as NULL.
            # Never substitute registry defaults or publication time for evidence.
            for relation, required_columns in _REQUIRED_CONTEXT_COLUMNS.items():
                if relation not in existing:
                    continue
                schema, table = relation.split(".")
                columns = {
                    row[0]
                    for row in connection.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = ? AND table_name = ?",
                        [schema, table],
                    ).fetchall()
                }
                missing = sorted(set(required_columns) - columns)
                checks[f"{relation}_missing_context_columns"] = missing
                reasons.extend(
                    f"missing_column:{relation}.{column}" for column in missing
                )
            if all(
                checks.get(f"{relation}_present") for relation in _REQUIRED_RELATIONS
            ):
                serp_count = connection.execute(
                    "SELECT count(*) FROM analytics.gold_serp_brand_visibility"
                ).fetchone()[0]
                llm_count = connection.execute(
                    "SELECT count(*) FROM analytics.gold_llm_brand_visibility"
                ).fetchone()[0]
                comparison_count = connection.execute(
                    "SELECT count(*) FROM analytics.gold_comparison_brand_metrics"
                ).fetchone()[0]
                checks["serp_metric_rows"] = serp_count
                checks["llm_metric_rows"] = llm_count
                checks["comparison_metric_rows"] = comparison_count
                if serp_count == 0:
                    reasons.append("empty_gold_serp_brand_visibility")
                if llm_count == 0:
                    reasons.append("empty_gold_llm_brand_visibility")
                if comparison_count == 0:
                    reasons.append("empty_gold_comparison_brand_metrics")
                invalid_available = connection.execute(
                    """
                    SELECT count(*) FROM (
                        SELECT metric_id FROM analytics.gold_serp_brand_visibility
                        WHERE availability_status = 'available' AND metric_value IS NULL
                        UNION ALL
                        SELECT metric_id FROM analytics.gold_llm_brand_visibility
                        WHERE availability_status = 'available' AND metric_value IS NULL
                        UNION ALL
                        SELECT metric_id FROM analytics.gold_comparison_brand_metrics
                        WHERE availability_status = 'available' AND metric_value IS NULL
                    )
                    """
                ).fetchone()[0]
                invalid_unavailable = connection.execute(
                    """
                    SELECT count(*) FROM (
                        SELECT metric_id FROM analytics.gold_serp_brand_visibility
                                                WHERE availability_status <> 'available'
                                                    AND metric_value IS NOT NULL
                        UNION ALL
                        SELECT metric_id FROM analytics.gold_llm_brand_visibility
                                                WHERE availability_status <> 'available'
                                                    AND metric_value IS NOT NULL
                        UNION ALL
                        SELECT metric_id FROM analytics.gold_comparison_brand_metrics
                                                WHERE availability_status <> 'available'
                                                    AND metric_value IS NOT NULL
                    )
                    """
                ).fetchone()[0]
                checks["available_null_metric_value_rows"] = invalid_available
                checks["unavailable_non_null_metric_value_rows"] = invalid_unavailable
                if invalid_available:
                    reasons.append("available_metric_value_null")
                if invalid_unavailable:
                    reasons.append("unavailable_metric_value_present")
            comparison_table = (
                "analytics.stg_reference__comparisons"
                if "analytics.stg_reference__comparisons" in existing
                else "bronze.comparison_registry"
                if "bronze.comparison_registry" in existing
                else None
            )
            checks["comparison_registry_relation"] = comparison_table
            if comparison_table is None:
                reasons.append("missing_comparison_registry")
                active_comparisons = 0
            else:
                active_comparisons = connection.execute(
                    f"SELECT count(*) FROM {comparison_table} WHERE active = true"
                ).fetchone()[0]
            checks["active_comparisons"] = active_comparisons
            if active_comparisons == 0:
                reasons.append("no_active_comparisons")
            elif checks.get("analytics.gold_comparison_brand_metrics_present"):
                missing_comparisons = connection.execute(
                    f"""
                    SELECT count(*) FROM {comparison_table} AS registry
                    WHERE registry.active = true
                      AND NOT EXISTS (
                        SELECT 1
                        FROM analytics.gold_comparison_brand_metrics AS gold
                        WHERE gold.comparison_id = registry.comparison_id
                      )
                    """
                ).fetchone()[0]
                checks["active_comparisons_missing_gold"] = missing_comparisons
                if missing_comparisons:
                    reasons.append("active_comparison_missing_gold_metrics")
        return ReleaseCompletenessReport(
            complete=not reasons,
            reasons=tuple(reasons),
            checks=checks,
        )

    def complete(
        self,
        release_id: str,
        *,
        notes: str | None = None,
        metric_version: str = _METRIC_VERSION,
        evidence: tuple[ApprovedEvidence, ...] = (),
        research_comparisons: tuple[Comparison, ...] | None = None,
    ) -> ReleaseCompletenessReport:
        """Snapshot Gold into presentation tables only when completeness passes."""
        if not release_id.strip():
            raise ValueError("release_id must not be blank")
        # Reject existing completed IDs before initialization/migrations can write.
        if self.database.path.exists():
            with duckdb.connect(str(self.database.path), read_only=True) as connection:
                exists = connection.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='presentation' AND table_name='releases'"
                ).fetchone()[0]
                if exists:
                    self._reject_completed(connection, release_id)
        self._initialize()
        created_at = datetime.now(UTC)
        with self.database.transaction() as connection:
            # Recheck within the writer transaction to prevent a check/write race.
            self._reject_completed(connection, release_id)
            report = self.assess(connection)
            connection.execute(
                "INSERT OR REPLACE INTO presentation.releases "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    release_id,
                    "incomplete" if not report.complete else "draft",
                    created_at,
                    None,
                    metric_version,
                    notes,
                    json.dumps(report.as_dict(), sort_keys=True),
                ],
            )
            if report.complete:
                self._publish(connection, release_id, report)
                publish_evidence(connection, release_id, evidence)
                if research_comparisons is not None:
                    publish_research(connection, release_id, research_comparisons)
        if not report.complete:
            raise ReleaseIncompleteError(
                "release is incomplete: " + ", ".join(report.reasons)
            )
        return report

    @staticmethod
    def _reject_completed(
        connection: duckdb.DuckDBPyConnection, release_id: str,
    ) -> None:
        row = connection.execute(
            "SELECT status FROM presentation.releases WHERE release_id = ?",
            [release_id],
        ).fetchone()
        if row and row[0] == "completed":
            raise ReleaseImmutableError(f"completed release is immutable: {release_id}")

    @staticmethod
    def _publish(
        connection: duckdb.DuckDBPyConnection,
        release_id: str,
        report: ReleaseCompletenessReport,
    ) -> None:
        """Copy the assessed source and advance the pointer in the same transaction."""
        # Keep the existing fixed-column snapshot contract for legacy releases.
        if report.complete:
            connection.execute(
                "DELETE FROM presentation.release_serp_brand_visibility "
                "WHERE release_id = ?",
                [release_id],
            )
            connection.execute(
                "DELETE FROM presentation.release_llm_brand_visibility "
                "WHERE release_id = ?",
                [release_id],
            )
            connection.execute(
                "DELETE FROM presentation.release_comparison_brand_metrics "
                "WHERE release_id = ?",
                [release_id],
            )
            connection.execute(
                """
                INSERT INTO presentation.release_serp_brand_visibility
                (release_id, metric_id, observation_id, query_id, brand_id,
                 brand_canonical_name, provider, search_engine, search_type,
                 collection_window, source_category, metric_name, metric_version,
                 numerator, denominator, metric_value, availability_status,
                 collection_status, has_results, best_normalized_rank,
                 response_id, raw_file_hash, language_code, location_code,
                 raw_language_code, raw_location_code, device, collected_at)
                SELECT ?, metric_id, observation_id, query_id, brand_id,
                       brand_canonical_name, provider, search_engine, search_type,
                       collection_window, source_category, metric_name, metric_version,
                       numerator, denominator, metric_value, availability_status,
                       collection_status, has_results, best_normalized_rank,
                       response_id, raw_file_hash, language_code, location_code,
                       raw_language_code, raw_location_code, device, collected_at
                FROM analytics.gold_serp_brand_visibility
                """,
                [release_id],
            )
            connection.execute(
                """
                INSERT INTO presentation.release_llm_brand_visibility
                (release_id, metric_id, observation_id, prompt_id, brand_id,
                 brand_canonical_name, provider, platform, model_name,
                 source_category, metric_name, metric_version, numerator,
                 denominator, metric_value, availability_status,
                 collection_status, mention_count, citation_count,
                 request_id, response_id, raw_file_hash, language_code,
                 location_code, raw_language_code, raw_location_code,
                 collection_window, collected_at)
                SELECT ?, metric_id, observation_id, prompt_id, brand_id,
                       brand_canonical_name, provider, platform, model_name,
                       source_category, metric_name, metric_version, numerator,
                       denominator, metric_value, availability_status,
                       collection_status, mention_count, citation_count,
                       request_id, response_id, raw_file_hash, language_code,
                       location_code, raw_language_code, raw_location_code,
                       collection_window, collected_at
                FROM analytics.gold_llm_brand_visibility
                """,
                [release_id],
            )
            connection.execute(
                """
                INSERT INTO presentation.release_comparison_brand_metrics
                (release_id, metric_id, comparison_id, query_id, prompt_id, brand_id,
                 brand_canonical_name, metric_name, metric_version,
                 serp_observation_id, llm_observation_id,
                 serp_availability_status, llm_availability_status,
                 serp_collection_status, llm_collection_status,
                 serp_numerator, serp_denominator, serp_metric_value,
                 llm_numerator, llm_denominator, llm_metric_value,
                 metric_value, availability_status, language_code, location_code,
                 serp_provider, search_engine, search_type, device, llm_provider,
                 platform, model_name, collection_window, serp_collected_at,
                 llm_collected_at, comparison_eligibility)
                SELECT ?, metric_id, comparison_id, query_id, prompt_id, brand_id,
                       brand_canonical_name, metric_name, metric_version,
                       serp_observation_id, llm_observation_id,
                       serp_availability_status, llm_availability_status,
                       serp_collection_status, llm_collection_status,
                       serp_numerator, serp_denominator, serp_metric_value,
                       llm_numerator, llm_denominator, llm_metric_value,
                       metric_value, availability_status, language_code, location_code,
                       serp_provider, search_engine, search_type, device, llm_provider,
                       platform, model_name, collection_window, serp_collected_at,
                       llm_collected_at, comparison_eligibility
                FROM analytics.gold_comparison_brand_metrics
                """,
                [release_id],
            )
            connection.execute(
                "UPDATE presentation.releases "
                "SET status = 'completed', completed_at = current_timestamp, "
                "completeness_json = ? WHERE release_id = ?",
                [json.dumps(report.as_dict(), sort_keys=True), release_id],
            )
            connection.execute(
                "INSERT OR REPLACE INTO presentation.release_current VALUES (?, ?)",
                [_CURRENT_SLOT, release_id],
            )
    def current_release_id(self) -> str | None:
        """Return the completed current release identifier, if any."""
        self._initialize()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT current_slot.release_id "
                "FROM presentation.release_current AS current_slot "
                "JOIN presentation.releases AS releases "
                  "ON releases.release_id = current_slot.release_id "
                "WHERE current_slot.slot = ? AND releases.status = 'completed'",
                [_CURRENT_SLOT],
            ).fetchone()
        return None if row is None else str(row[0])

    def get(self, release_id: str) -> ReleaseRecord | None:
        self._initialize()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT release_id, status, metric_version, notes, "
                "created_at, completed_at "
                "FROM presentation.releases WHERE release_id = ?",
                [release_id],
            ).fetchone()
        if row is None:
            return None
        return ReleaseRecord(*row)
