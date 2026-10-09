from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from geo_research.collection.standard_serp import (
    StandardSERPAssignment,
    StandardSERPCollector,
    task_retrieval_endpoint,
    tasks_ready_endpoint,
)
from geo_research.connectors.dataforseo.envelope import ProviderEnvelope
from geo_research.domain.serp import Query, SearchTarget
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.raw_store import RawStore
from geo_research.storage.repositories import RawEvidenceRepository


def test_standard_collection_retrieves_once_and_persists_bronze(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")
    calls: list[tuple[str, str]] = []

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        calls.append((method, url))
        assert method == "POST"
        assert isinstance(payload, list)
        assert payload[0]["tag"] == "geo:2026-09-25:query-1:target-1"
        return ProviderEnvelope(
            payload={
                "tasks": [
                    {"id": "task-123", "status_code": 20100, "cost": 0.0006}
                ]
            },
            correlation_id="post-correlation",
        )

    collector = StandardSERPCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    )
    result = collector.collect(
        StandardSERPAssignment(
            Query(
                query_id="query-1",
                keyword="example query",
                language="en",
                market="US",
                active=True,
            ),
            SearchTarget(
                search_target_id="target-1",
                provider="dataforseo",
                search_engine="google",
                search_type="organic",
                retrieval_method="standard",
                location_code="2840",
                language_code="en",
                device="desktop",
                operating_system="windows",
                depth=10,
                active=True,
            ),
        ),
        run_id="run-1",
        collection_window="2026-09-25",
        estimated_cost_usd=0.001,
        now=datetime(2026, 9, 25, tzinfo=UTC),
    )

    assert calls == [
        (
            "POST",
            "https://api.dataforseo.com/v3/serp/google/organic/task_post",
        ),
    ]
    assert result.task_id == "task-123"
    with database.transaction() as connection:
        request_row = connection.execute(
            "SELECT request_status, query_id, search_target_id, collection_window, "
            "request_hash "
            "FROM bronze.api_requests"
        ).fetchone()
        attempt_count = connection.execute(
            "SELECT count(*) FROM bronze.api_attempts"
        ).fetchone()[0]
        response_row = connection.execute(
            "SELECT provider_request_id, task_id, actual_cost FROM bronze.api_responses"
        ).fetchone()
        raw_count = connection.execute(
            "SELECT count(*) FROM bronze.raw_files"
        ).fetchone()[0]
    assert request_row[:4] == (
        "submitted_pending_result",
        "query-1",
        "target-1",
        "2026-09-25",
    )
    assert request_row[4]
    assert attempt_count == 1
    assert response_row == (None, "task-123", 0.0006)
    assert raw_count == 2

    repository = RawEvidenceRepository(database, raw_store)
    assert repository.submitted_serp_assignment_keys("2026-09-25") == {
        ("query-1", "target-1")
    }
    assert repository.submitted_serp_assignment_keys("another-window") == set()


def test_ready_task_is_retrieved_once_without_resubmission(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")
    phase = "post"
    calls: list[tuple[str, str]] = []

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        nonlocal phase
        calls.append((method, url))
        if phase == "post":
            phase = "retrieve"
            return ProviderEnvelope(
                payload={
                    "tasks": [
                        {"id": "task-123", "status_code": 20100, "cost": 0.0006}
                    ]
                },
                correlation_id="post-correlation",
            )
        if url.endswith("tasks_ready"):
            return ProviderEnvelope(
                payload={"tasks": [{"result": [{"id": "task-123"}]}]},
                correlation_id="ready-correlation",
            )
        return ProviderEnvelope(
            payload={
                "tasks": [
                    {
                        "id": "task-123",
                        "status_code": 40102,
                        "status_message": "No Search Results.",
                        "result": [{"items": []}],
                    }
                ]
            },
            correlation_id="get-correlation",
        )

    collector = StandardSERPCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    )
    collector.collect(
        _assignment(),
        run_id="run-1",
        collection_window="2026-09-25",
        estimated_cost_usd=0.001,
        now=datetime(2026, 9, 25, tzinfo=UTC),
    )

    assert collector.retrieve_ready(now=datetime(2026, 9, 25, tzinfo=UTC)) == [
        "task-123"
    ]
    assert [method for method, _ in calls] == ["POST", "GET", "GET"]
    with database.transaction() as connection:
        status = connection.execute(
            "SELECT request_status FROM bronze.api_requests "
            "WHERE request_id = (SELECT request_id FROM bronze.api_requests "
            "WHERE request_status = 'completed' LIMIT 1)"
        ).fetchone()[0]
    assert status == "completed"


def test_completed_task_missing_from_ready_list_is_checked_directly(
    tmp_path: Path,
) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")
    phase = "post"
    calls: list[tuple[str, str]] = []

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        nonlocal phase
        calls.append((method, url))
        if phase == "post":
            phase = "retrieve"
            return ProviderEnvelope(
                payload={
                    "tasks": [
                        {"id": "task-123", "status_code": 20100, "cost": 0.0006}
                    ]
                },
                correlation_id="post-correlation",
            )
        if url.endswith("tasks_ready"):
            return ProviderEnvelope(
                payload={"tasks": [{"result": []}]},
                correlation_id="ready-correlation",
            )
        return ProviderEnvelope(
            payload={"tasks": [{"id": "task-123", "status_code": 20000, "result": []}]},
            correlation_id="get-correlation",
        )

    collector = StandardSERPCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    )
    collector.collect(
        _assignment(),
        run_id="run-1",
        collection_window="2026-10",
        estimated_cost_usd=0.001,
        now=datetime(2026, 10, 5, tzinfo=UTC),
    )

    assert collector.retrieve_ready() == ["task-123"]
    assert [method for method, _ in calls] == ["POST", "GET", "GET"]


def test_standard_retrieval_endpoints_cover_all_supported_engines() -> None:
    for search_engine in ("google", "Bing", "Yahoo", "Baidu"):
        engine = search_engine.casefold()
        assert tasks_ready_endpoint(search_engine).endswith(
            f"/serp/{engine}/organic/tasks_ready"
        )
        assert task_retrieval_endpoint(search_engine, "task-123").endswith(
            f"/serp/{engine}/organic/task_get/advanced/task-123"
        )


def test_pending_standard_tasks_accept_registry_engine_casing(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        return ProviderEnvelope(
            payload={
                "tasks": [
                    {"id": "task-123", "status_code": 20100, "cost": 0.0006}
                ]
            },
            correlation_id="post-correlation",
        )

    assignment = _assignment()
    assignment.target.search_engine = "Bing"
    StandardSERPCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    ).collect(
        assignment,
        run_id="run-1",
        collection_window="2026-10",
        estimated_cost_usd=0.001,
        now=datetime(2026, 10, 5, tzinfo=UTC),
    )

    pending = RawEvidenceRepository(database, raw_store).pending_standard_serp_tasks()
    assert len(pending) == 1
    assert pending[0].search_engine == "Bing"


def _assignment() -> StandardSERPAssignment:
    return StandardSERPAssignment(
        Query(
            query_id="query-1",
            keyword="example query",
            language="en",
            market="US",
            active=True,
        ),
        SearchTarget(
            search_target_id="target-1",
            provider="dataforseo",
            search_engine="google",
            search_type="organic",
            retrieval_method="standard",
            location_code="2840",
            language_code="en",
            device="desktop",
            operating_system="windows",
            depth=10,
            active=True,
        ),
    )
