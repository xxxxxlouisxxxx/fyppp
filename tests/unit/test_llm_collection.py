from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from geo_research.collection.llm_collector import (
    LLMCollectionAssignment,
    LLMCollector,
)
from geo_research.connectors.dataforseo.envelope import ProviderEnvelope
from geo_research.connectors.dataforseo.errors import DataForSEOTimeoutError
from geo_research.domain.llm import LLMPrompt, LLMTarget
from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.raw_store import RawStore
from geo_research.storage.repositories import RawEvidenceRepository


def test_task_post_collection_persists_pending_bronze(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")
    calls: list[tuple[str, str, object | None]] = []

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        calls.append((method, url, payload))
        return ProviderEnvelope(
            payload={"tasks": [{"id": "task-123", "cost": 0.008}]},
            provider_request_id="provider-request-123",
            correlation_id="correlation-123",
        )

    result = LLMCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    ).collect(
        LLMCollectionAssignment(
            LLMPrompt(
                prompt_id="prompt-1",
                prompt_text="comfortable walking sneakers",
                language="en",
                market="US",
                active=True,
            ),
            LLMTarget(
                llm_target_id="llm-target-1",
                provider="dataforseo",
                platform="chat_gpt",
                model_name="chat_gpt",
                endpoint_name="ai_optimization/chat_gpt/llm_scraper/live/advanced",
                location_code="2840",
                language_code="en",
                active=True,
            ),
        ),
        run_id="llm-run-1",
        collection_window="2026-09-25",
        estimated_cost_usd=0.01,
        now=datetime(2026, 9, 25, tzinfo=UTC),
    )

    assert result.request_id
    assert calls == [
        (
            "POST",
            "https://api.dataforseo.com/v3/ai_optimization/chat_gpt/llm_scraper/task_post",
            [
                {
                    "keyword": "comfortable walking sneakers",
                    "location_code": 2840,
                    "language_code": "en",
                    "tag": "llm:2026-09-25:prompt-1:llm-target-1",
                    "force_web_search": True,
                }
            ],
        )
    ]
    with database.transaction() as connection:
        request_row = connection.execute(
            "SELECT source_category, platform, model_name, request_status, "
            "estimated_cost FROM bronze.api_requests"
        ).fetchone()
        response_row = connection.execute(
            "SELECT provider_request_id, actual_cost FROM bronze.api_responses"
        ).fetchone()
        raw_count = connection.execute(
            "SELECT count(*) FROM bronze.raw_files"
        ).fetchone()[0]
    assert result.task_id == "task-123"
    assert request_row == (
        "llm",
        "chat_gpt",
        "chat_gpt",
        "submitted_pending_result",
        0.01,
    )
    assert response_row == ("provider-request-123", 0.008)
    assert raw_count == 2


def test_gemini_task_post_uses_the_gemini_scraper_contract(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")
    calls: list[tuple[str, str, object | None]] = []

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        calls.append((method, url, payload))
        return ProviderEnvelope(
            correlation_id="synthetic-gemini-test",
            payload={"tasks": [{"id": "task-gemini"}]},
        )

    LLMCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    ).collect(
        LLMCollectionAssignment(
            LLMPrompt(
                prompt_id="prompt-1",
                prompt_text="comfortable walking sneakers",
                language="en",
                market="US",
                active=True,
            ),
            LLMTarget(
                llm_target_id="gemini-target-1",
                provider="dataforseo",
                platform="gemini",
                model_name="gemini",
                endpoint_name="ai_optimization/gemini/llm_scraper/task_post",
                location_code="2840",
                language_code="en",
                active=True,
            ),
        ),
        run_id="gemini-run-1",
        collection_window="2026-09-27",
        estimated_cost_usd=0.01,
        now=datetime(2026, 9, 27, tzinfo=UTC),
    )

    assert calls == [
        (
            "POST",
            "https://api.dataforseo.com/v3/ai_optimization/gemini/llm_scraper/task_post",
            [
                {
                    "keyword": "comfortable walking sneakers",
                    "location_code": 2840,
                    "language_code": "en",
                    "tag": "llm:2026-09-27:prompt-1:gemini-target-1",
                }
            ],
        )
    ]


def test_ready_llm_task_is_retrieved_without_reposting(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")
    calls: list[tuple[str, str]] = []

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        calls.append((method, url))
        if method == "POST":
            return ProviderEnvelope(
                payload={"tasks": [{"id": "task-123", "cost": 0.008}]},
                correlation_id="post-correlation",
            )
        if url.endswith("tasks_ready"):
            return ProviderEnvelope(
                payload={"tasks": [{"result": [{"id": "task-123"}]}]},
                correlation_id="ready-correlation",
            )
        return ProviderEnvelope(
            payload={"tasks": [{"id": "task-123", "status_code": 20000, "result": []}]},
            correlation_id="get-correlation",
        )

    collector = LLMCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    )
    collector.collect(
        _assignment(),
        run_id="llm-run-1",
        collection_window="2026-09-25",
        estimated_cost_usd=0.01,
        now=datetime(2026, 9, 25, tzinfo=UTC),
    )

    assert collector.retrieve_ready(now=datetime(2026, 9, 25, tzinfo=UTC)) == [
        "task-123"
    ]
    assert [method for method, _ in calls] == ["POST", "GET", "GET"]
    with database.transaction() as connection:
        statuses = connection.execute(
            "SELECT request_status FROM bronze.api_requests ORDER BY created_at"
        ).fetchall()
    assert statuses == [("completed",), ("completed",)]


def test_completed_llm_task_missing_from_ready_list_is_retrieved(
    tmp_path: Path,
) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")
    calls: list[tuple[str, str]] = []

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        calls.append((method, url))
        if method == "POST":
            return ProviderEnvelope(
                payload={"tasks": [{"id": "task-123"}]},
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

    collector = LLMCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    )
    collector.collect(
        _assignment(),
        run_id="llm-run-1",
        collection_window="2026-09-25",
        estimated_cost_usd=0.01,
        now=datetime(2026, 9, 25, tzinfo=UTC),
    )

    assert collector.retrieve_ready(now=datetime(2026, 9, 25, tzinfo=UTC)) == [
        "task-123"
    ]
    assert [method for method, _ in calls] == ["POST", "GET", "GET"]


def test_live_chat_gpt_timeout_does_not_write_evidence(tmp_path: Path) -> None:
    database = DuckDBStore(tmp_path / "warehouse.duckdb")
    database.initialize()
    raw_store = RawStore(tmp_path / "raw")

    def request(method: str, url: str, payload: object | None) -> ProviderEnvelope:
        raise DataForSEOTimeoutError("DataForSEO timeout; correlation_id=test")

    collector = LLMCollector(
        RawEvidenceRepository(database, raw_store), raw_store, request
    )

    with pytest.raises(DataForSEOTimeoutError, match="correlation_id=test"):
        collector.collect(
            _assignment(),
            run_id="llm-run-1",
            collection_window="2026-09-25",
            estimated_cost_usd=0.01,
            now=datetime(2026, 9, 25, tzinfo=UTC),
        )

    with database.transaction() as connection:
        raw_count = connection.execute(
            "SELECT count(*) FROM bronze.raw_files"
        ).fetchone()[0]
        request_count = connection.execute(
            "SELECT count(*) FROM bronze.api_requests"
        ).fetchone()[0]
    assert raw_count == 0
    assert request_count == 0
    assert raw_store.evidence_directories() == set()


def _assignment() -> LLMCollectionAssignment:
    return LLMCollectionAssignment(
        LLMPrompt(
            prompt_id="prompt-1",
            prompt_text="comfortable walking sneakers",
            language="en",
            market="US",
            active=True,
        ),
        LLMTarget(
            llm_target_id="llm-target-1",
            provider="dataforseo",
            platform="chat_gpt",
            model_name="chat_gpt",
            endpoint_name="ai_optimization/chat_gpt/llm_scraper/task_post",
            location_code="2840",
            language_code="en",
            active=True,
        ),
    )
