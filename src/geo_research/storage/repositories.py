"""Bronze metadata repositories; raw response blobs never enter these tables."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from geo_research.parsers.serp.contracts import SERPParseResult
from geo_research.parsers.serp.features import SERPFeatureResult
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.raw_store import RawEvidence, RawStore, RawWriteResult


@dataclass(frozen=True, slots=True)
class StorageVerificationReport:
    """Recovery-relevant differences between committed metadata and raw files."""

    missing_raw_directories: tuple[str, ...]
    unreferenced_raw_directories: tuple[Path, ...]

    @property
    def valid(self) -> bool:
        return (
            not self.missing_raw_directories and not self.unreferenced_raw_directories
        )


@dataclass(frozen=True, slots=True)
class PendingSERPTask:
    """The stored context required to retrieve one standard provider task."""

    request_id: str
    task_id: str
    query_id: str
    search_target_id: str
    collection_window: str
    provider: str
    search_engine: str


@dataclass(frozen=True, slots=True)
class PendingLLMTask:
    """The stored context required to retrieve one LLM Scraper task."""

    request_id: str
    task_id: str
    prompt_id: str
    llm_target_id: str
    collection_window: str
    provider: str
    platform: str
    model_name: str | None


@dataclass(frozen=True, slots=True)
class SilverLLMObservation:
    """Flattened LLM evidence persisted without guessing item-level schemas."""

    observation_id: str
    request_id: str
    response_id: str
    provider: str
    platform: str
    model_name: str
    query_text: str | None
    task_id: str | None
    status_code: int | None
    cost: float | None
    language_code: str | None
    location_code: str | None
    items_count: int
    response_text: str | None
    items_json: str
    citations_json: str
    raw_file_hash: str
    parser_name: str
    parser_version: str
    outcome_status: str


class RawEvidenceRepository:
    """Records raw artifact metadata after the RawStore finalized all files."""

    def __init__(self, database: DuckDBStore, raw_store: RawStore) -> None:
        self.database = database
        self.raw_store = raw_store

    def record(self, evidence: RawEvidence, result: RawWriteResult) -> None:
        """Commit request, response, and file metadata in one transaction.

        Call only after `RawStore.write`; raw files are never rewritten if this
        transaction fails, making the incomplete relationship recoverable.
        """
        self.record_many(((evidence, result),))

    def record_many(
        self,
        records: Iterable[tuple[RawEvidence, RawWriteResult]],
    ) -> None:
        """Commit multiple finalized Raw artifacts in one metadata transaction."""
        with self.database.transaction() as connection:
            for evidence, result in records:
                self._record_in_transaction(connection, evidence, result)

    def _record_in_transaction(
        self,
        connection: object,
        evidence: RawEvidence,
        result: RawWriteResult,
    ) -> None:
        """Write one evidence record using the caller-owned database transaction."""
        connection.execute(
            "INSERT OR IGNORE INTO bronze.ingestion_runs VALUES (?, ?, ?, ?)",
            [
                evidence.run_id,
                evidence.request_status,
                evidence.collected_at,
                evidence.collected_at,
            ],
        )
        connection.execute(
            "INSERT INTO bronze.api_requests "
            "(request_id, run_id, source_category, provider, platform, "
            "search_engine, model_name, request_status, estimated_cost, "
            "created_at, query_id, search_target_id, collection_window, "
            "request_hash, deduplication_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                evidence.request_id,
                evidence.run_id,
                evidence.source_category,
                evidence.provider,
                (evidence.platform_or_engine
                 if evidence.source_category == "llm" else None),
                (evidence.platform_or_engine
                 if evidence.source_category == "serp" else None),
                evidence.model_name,
                evidence.request_status,
                evidence.estimated_cost_usd,
                evidence.collected_at,
                evidence.query_id,
                evidence.search_target_id,
                evidence.collection_window,
                evidence.request_hash,
                evidence.deduplication_key,
            ],
        )
        for attempt in evidence.attempts:
            connection.execute(
                "INSERT INTO bronze.api_attempts VALUES (?, ?, ?, ?, ?, ?)",
                [
                    attempt["attempt_id"],
                    evidence.request_id,
                    attempt["attempt_number"],
                    attempt["started_at"],
                    attempt["ended_at"],
                    attempt["transport_status"],
                ],
            )
        connection.execute(
            "INSERT INTO bronze.api_responses "
            "(response_id, request_id, provider_request_id, response_valid, "
            "actual_cost, received_at, task_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                f"{evidence.request_id}-response",
                evidence.request_id,
                evidence.provider_request_id,
                True,
                evidence.actual_cost_usd,
                evidence.collected_at,
                _task_id_from_response(evidence.response_payload),
            ],
        )
        for artifact_type, artifact in (
            ("request", result.request),
            ("response", result.response),
        ):
            connection.execute(
                "INSERT INTO bronze.raw_files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    f"{evidence.request_id}-{artifact_type}",
                    evidence.request_id,
                    artifact_type,
                    str(result.directory),
                    str(artifact.path.relative_to(self.raw_store.root)),
                    artifact.sha256,
                    artifact.byte_size,
                    artifact.content_type,
                    evidence.collected_at,
                ],
            )

    def verify(self) -> StorageVerificationReport:
        """Detect committed rows without files and files without committed rows."""
        referenced = self.database.fetch_raw_directories()
        actual = self.raw_store.evidence_directories()
        actual_strings = {str(path) for path in actual}
        return StorageVerificationReport(
            missing_raw_directories=tuple(sorted(referenced - actual_strings)),
            unreferenced_raw_directories=tuple(
                sorted(
                    (path for path in actual if str(path) not in referenced), key=str
                )
            ),
        )

    def pending_google_tasks(self) -> list[PendingSERPTask]:
        """Return submitted Google tasks that have not had results retrieved."""
        return [
            task
            for task in self.pending_standard_serp_tasks()
            if task.search_engine == "google"
        ]

    def pending_standard_serp_tasks(self) -> list[PendingSERPTask]:
        """Return submitted supported Standard SERP tasks awaiting retrieval."""
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT request_id, task_id, query_id, search_target_id, "
                "collection_window, provider, search_engine "
                "FROM bronze.api_requests requests "
                "JOIN bronze.api_responses responses USING (request_id) "
                "WHERE request_status = 'submitted_pending_result' "
                "AND source_category = 'serp' AND provider = 'dataforseo' "
                "AND lower(search_engine) IN ('google', 'bing', 'yahoo', 'baidu') "
                "AND task_id IS NOT NULL"
            ).fetchall()
        return [PendingSERPTask(*row) for row in rows]

    def submitted_serp_assignment_keys(
        self, collection_window: str
    ) -> set[tuple[str, str]]:
        """Return query-target pairs already accepted in a collection window."""
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT DISTINCT query_id, search_target_id "
                "FROM bronze.api_requests requests "
                "JOIN bronze.api_responses responses USING (request_id) "
                "WHERE source_category = 'serp' AND provider = 'dataforseo' "
                "AND collection_window = ? "
                "AND request_status IN ('submitted_pending_result', 'completed') "
                "AND task_id IS NOT NULL AND actual_cost > 0",
                [collection_window],
            ).fetchall()
        return {(str(query_id), str(target_id)) for query_id, target_id in rows}

    def submitted_llm_assignment_keys(
        self, collection_window: str
    ) -> set[tuple[str, str]]:
        """Return prompt-target pairs already accepted in a collection window."""
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT DISTINCT query_id, search_target_id "
                "FROM bronze.api_requests requests "
                "JOIN bronze.api_responses responses USING (request_id) "
                "WHERE source_category = 'llm' AND provider = 'dataforseo' "
                "AND collection_window = ? AND request_hash IS NOT NULL "
                "AND request_status IN ('submitted_pending_result', 'completed') "
                "AND task_id IS NOT NULL AND actual_cost > 0",
                [collection_window],
            ).fetchall()
        return {(str(prompt_id), str(target_id)) for prompt_id, target_id in rows}

    def mark_task_retrieved(self, request_id: str) -> None:
        """Mark an original task as retrieved after its result evidence commits."""
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE bronze.api_requests SET request_status = 'completed' "
                "WHERE request_id = ?",
                [request_id],
            )

    def pending_llm_tasks(self) -> list[PendingLLMTask]:
        """Return submitted ChatGPT LLM Scraper tasks without result evidence."""
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT request_id, task_id, query_id, search_target_id, "
                "collection_window, provider, platform, model_name "
                "FROM bronze.api_requests requests "
                "JOIN bronze.api_responses responses USING (request_id) "
                "WHERE request_status = 'submitted_pending_result' "
                "AND source_category = 'llm' AND provider = 'dataforseo' "
                "AND platform IN ('chat_gpt', 'gemini') AND task_id IS NOT NULL"
            ).fetchall()
        return [PendingLLMTask(*row) for row in rows]


def _task_id_from_response(payload: dict[str, object]) -> str | None:
    """Extract only the documented first task ID from persisted evidence."""
    envelope = payload.get("retrieval", payload.get("post"))
    if not isinstance(envelope, dict):
        return None
    tasks = envelope.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        return None
    task_id = tasks[0].get("id")
    return task_id if isinstance(task_id, str) else None


class SilverSERPRepository:
    """Persists traceable Phase 8 SERP parser outputs without parsing LLM evidence."""

    def __init__(self, database: DuckDBStore) -> None:
        self.database = database

    def record(self, result: SERPParseResult) -> None:
        """Write one observation, its top-level items, and every quarantine record."""
        self.record_many((result,))

    def record_many(self, results: Iterable[SERPParseResult]) -> None:
        """Write multiple parser outputs in one transaction."""
        with self.database.transaction() as connection:
            for result in results:
                self._record_in_transaction(connection, result)

    def _record_in_transaction(
        self, connection: object, result: SERPParseResult
    ) -> None:
        observation = result.observation
        connection.execute(
            "INSERT OR IGNORE INTO silver.silver_search_observations "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                observation.observation_id,
                observation.query_id,
                observation.provider,
                observation.search_engine,
                observation.search_type,
                observation.location_code,
                observation.language_code,
                observation.device,
                observation.collection_window,
                observation.response_id,
                observation.source_ingestion_id,
                observation.raw_file_hash,
                observation.has_results,
                observation.outcome_status,
            ],
        )
        for item in result.items:
            connection.execute(
                "INSERT OR IGNORE INTO silver.silver_serp_items "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    item.serp_item_id,
                    item.observation_id,
                    item.engine,
                    item.response_id,
                    item.source_ingestion_id,
                    item.raw_file_hash,
                    item.item_index,
                    item.raw_item_type,
                    item.normalized_item_type,
                    item.rank_group,
                    item.rank_absolute,
                    item.page,
                    item.position,
                    item.raw_domain,
                    item.normalized_domain,
                    item.raw_url,
                    item.canonical_url,
                    item.title,
                    item.description,
                    item.raw_item_json,
                    item.parser_name,
                    item.parser_version,
                    item.rank_semantics_version,
                    item.normalization_status,
                    item.parsing_warning,
                ],
            )
        for record in result.quarantine:
            connection.execute(
                "INSERT OR IGNORE INTO silver.silver_serp_parsing_quarantine "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    record.quarantine_id,
                    record.observation_id,
                    record.engine,
                    record.response_id,
                    record.source_ingestion_id,
                    record.raw_file_hash,
                    record.item_index,
                    record.reason,
                    record.raw_item_json,
                    record.parser_name,
                    record.parser_version,
                ],
            )


class SilverSERPFeatureRepository:
    """Persists only fixture-proven SERP feature rows."""

    def __init__(self, database: DuckDBStore) -> None:
        self.database = database

    def record(self, result: SERPFeatureResult) -> None:
        """Write normalized organic rows; unsupported feature tables remain empty."""
        self.record_many((result,))

    def record_many(self, results: Iterable[SERPFeatureResult]) -> None:
        """Write normalized feature outputs in one transaction."""
        with self.database.transaction() as connection:
            for result in results:
                for organic in result.organic_results:
                    connection.execute(
                        "INSERT OR IGNORE INTO silver.silver_organic_results "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            organic.organic_result_id,
                            organic.provider,
                            organic.search_engine,
                            organic.search_type,
                            organic.observation_id,
                            organic.parent_serp_item_id,
                            organic.source_item_type,
                            organic.feature_supported,
                            organic.feature_observed,
                            organic.normalization_status,
                            organic.raw_evidence,
                            organic.engine_rank,
                            organic.normalized_rank,
                            organic.raw_url,
                            organic.canonical_url,
                            organic.title,
                            organic.description,
                        ],
                    )


class SilverLLMRepository:
    """Persists flattened LLM observations without inventing item parsers."""

    def __init__(self, database: DuckDBStore) -> None:
        self.database = database

    def record(self, observation: SilverLLMObservation) -> None:
        """Write one LLM observation or ignore an identical primary key."""
        self.record_many((observation,))

    def record_many(self, observations: Iterable[SilverLLMObservation]) -> None:
        """Write multiple flattened LLM observations in one transaction."""
        with self.database.transaction() as connection:
            for observation in observations:
                connection.execute(
                    "INSERT OR IGNORE INTO silver.silver_llm_observations "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        observation.observation_id,
                        observation.request_id,
                        observation.response_id,
                        observation.provider,
                        observation.platform,
                        observation.model_name,
                        observation.query_text,
                        observation.task_id,
                        observation.status_code,
                        observation.cost,
                        observation.language_code,
                        observation.location_code,
                        observation.items_count,
                        observation.response_text,
                        observation.items_json,
                        observation.citations_json,
                        observation.raw_file_hash,
                        observation.parser_name,
                        observation.parser_version,
                        observation.outcome_status,
                    ],
                )
