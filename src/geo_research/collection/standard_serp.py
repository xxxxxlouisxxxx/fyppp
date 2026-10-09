"""Controlled one-shot DataForSEO standard SERP collection."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from geo_research.adapters.serp.registry import SERP_ADAPTERS
from geo_research.collection.deduplication import SuccessfulDeduplicator
from geo_research.collection.identity import serp_request_hash
from geo_research.connectors.dataforseo.envelope import ProviderEnvelope
from geo_research.domain.serp import Query, SearchTarget
from geo_research.registries.validators import _parse_registry, validate_registries
from geo_research.storage.raw_store import RawEvidence, RawStore
from geo_research.storage.repositories import PendingSERPTask, RawEvidenceRepository

_API_BASE = "https://api.dataforseo.com/v3/serp"

ProviderRequest = Callable[
    [str, str, Mapping[str, object] | Sequence[Mapping[str, object]] | None],
    ProviderEnvelope,
]


@dataclass(frozen=True, slots=True)
class StandardSERPAssignment:
    """One resolved, active CSV assignment eligible for an adapter."""

    query: Query
    target: SearchTarget


@dataclass(frozen=True, slots=True)
class StandardSERPCollectionResult:
    """Non-secret outcome of a standard task submission."""

    request_id: str
    task_id: str


def _tagged_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    collection_window: str,
    query_id: str,
    search_target_id: str,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Return a provider-reconcilable copy of a task-post payload."""
    tag = f"geo:{collection_window}:{query_id}:{search_target_id}"
    if len(tag) > 255:
        raise ValueError("SERP task tag exceeds the provider's 255-character limit")
    if isinstance(payload, list):
        return [{**task, "tag": tag} for task in payload]
    return {**payload, "tag": tag}


def active_google_organic_assignments(
    queries: list[Query],
    targets: list[SearchTarget],
    assignments: list[tuple[str, str, bool]],
) -> list[StandardSERPAssignment]:
    """Resolve only active Google-organic assignment rows after registry validation."""
    query_by_id = {query.query_id: query for query in queries}
    target_by_id = {target.search_target_id: target for target in targets}
    return [
        StandardSERPAssignment(query_by_id[query_id], target_by_id[target_id])
        for query_id, target_id, active in assignments
        if active
        and target_by_id[target_id].provider == "dataforseo"
        and target_by_id[target_id].search_engine == "google"
        and target_by_id[target_id].search_type == "organic"
    ]


def active_standard_organic_assignments(
    queries: list[Query],
    targets: list[SearchTarget],
    assignments: list[tuple[str, str, bool]],
) -> list[StandardSERPAssignment]:
    """Resolve active assignments for every verified Standard organic adapter."""
    query_by_id = {query.query_id: query for query in queries}
    target_by_id = {target.search_target_id: target for target in targets}
    return [
        StandardSERPAssignment(query_by_id[query_id], target)
        for query_id, target_id, active in assignments
        if active
        and (target := target_by_id[target_id]).provider == "dataforseo"
        and target.search_type == "organic"
        and target.retrieval_method == "standard"
        and target.search_engine.casefold() in SERP_ADAPTERS
    ]


def load_active_google_organic_assignments(
    directory: str,
) -> list[StandardSERPAssignment]:
    """Load validated CSV records and return only active Google assignments."""
    from pathlib import Path

    from geo_research.domain.assignments import QueryTargetAssignment

    registry_directory = Path(directory)
    validate_registries(registry_directory)
    queries = cast(
        list[Query],
        _parse_registry(registry_directory, "queries.csv", Query, "query_id"),
    )
    targets = cast(
        list[SearchTarget],
        _parse_registry(
            registry_directory,
            "search_targets.csv",
            SearchTarget,
            "search_target_id",
        ),
    )
    assignments = cast(
        list[QueryTargetAssignment],
        _parse_registry(
            registry_directory,
            "query_target_assignments.csv",
            QueryTargetAssignment,
            "assignment_id",
        ),
    )
    return active_google_organic_assignments(
        queries,
        targets,
        [
            (assignment.query_id, assignment.search_target_id, assignment.active)
            for assignment in assignments
        ],
    )


def load_active_standard_organic_assignments(
    directory: str,
) -> list[StandardSERPAssignment]:
    """Load validated CSV records for every supported Standard organic engine."""
    from pathlib import Path

    from geo_research.domain.assignments import QueryTargetAssignment

    registry_directory = Path(directory)
    validate_registries(registry_directory)
    queries = cast(
        list[Query],
        _parse_registry(registry_directory, "queries.csv", Query, "query_id"),
    )
    targets = cast(
        list[SearchTarget],
        _parse_registry(
            registry_directory,
            "search_targets.csv",
            SearchTarget,
            "search_target_id",
        ),
    )
    assignments = cast(
        list[QueryTargetAssignment],
        _parse_registry(
            registry_directory,
            "query_target_assignments.csv",
            QueryTargetAssignment,
            "assignment_id",
        ),
    )
    return active_standard_organic_assignments(
        queries,
        targets,
        [
            (assignment.query_id, assignment.search_target_id, assignment.active)
            for assignment in assignments
        ],
    )


class StandardSERPCollector:
    """Posts a standard task and records its immutable submission evidence."""

    def __init__(
        self,
        repository: RawEvidenceRepository,
        raw_store: RawStore,
        request: ProviderRequest,
    ) -> None:
        self._repository = repository
        self._raw_store = raw_store
        self._request = request

    def collect(
        self,
        assignment: StandardSERPAssignment,
        *,
        run_id: str,
        collection_window: str,
        estimated_cost_usd: float | None,
        now: datetime | None = None,
    ) -> StandardSERPCollectionResult:
        """Perform exactly one verified task-post request without polling."""
        adapter = _adapter_for(assignment.target)
        post = adapter.build_payload(assignment.query, assignment.target)
        payload = _tagged_payload(
            post.payload,
            collection_window=collection_window,
            query_id=assignment.query.query_id,
            search_target_id=assignment.target.search_target_id,
        )
        request_id = str(uuid4())
        collected_at = now or datetime.now(UTC)
        request_hash = serp_request_hash(
            provider=assignment.target.provider,
            search_engine=assignment.target.search_engine,
            search_type=assignment.target.search_type,
            endpoint=post.endpoint,
            function="task_post",
            retrieval_method=assignment.target.retrieval_method,
            keyword=assignment.query.keyword,
            location=assignment.target.location_code,
            language=assignment.target.language_code,
            device=assignment.target.device,
            operating_system=assignment.target.operating_system,
            depth=assignment.target.depth,
            adapter_version=f"{adapter.search_engine}-organic-v1",
            capability_evidence_version=adapter.capability.evidence_version,
        )
        posted = self._request("POST", post.endpoint, payload)
        _assert_task_post_succeeded(posted.payload)
        task_id = _task_id(posted.payload)
        evidence = RawEvidence(
            source_category="serp",
            provider=assignment.target.provider,
            platform_or_engine=assignment.target.search_engine,
            run_id=run_id,
            request_id=request_id,
            collected_at=collected_at,
            query_id=str(assignment.query.query_id),
            search_target_id=str(assignment.target.search_target_id),
            collection_window=collection_window,
            request_hash=request_hash,
            deduplication_key=SuccessfulDeduplicator().key(
                "serp",
                assignment.target.provider,
                post.endpoint,
                request_hash,
                collection_window,
            ),
            estimated_cost_usd=estimated_cost_usd,
            provider_request_id=posted.provider_request_id,
            actual_cost_usd=_cost(posted.payload),
            request_status="submitted_pending_result",
            attempts=(_attempt(request_id, 1, collected_at, "post_completed"),),
            request_payload={"post": payload},
            response_payload={"post": posted.payload},
        )
        raw_result = self._raw_store.write(evidence)
        self._repository.record(evidence, raw_result)
        return StandardSERPCollectionResult(request_id, task_id)

    def retrieve_ready(
        self,
        *,
        now: datetime | None = None,
    ) -> list[str]:
        """Retrieve only locally pending task IDs returned by tasks_ready once."""
        pending = {
            task.task_id: task
            for task in self._repository.pending_standard_serp_tasks()
        }
        if not pending:
            return []
        retrieved_ids: list[str] = []
        for search_engine in sorted({task.search_engine for task in pending.values()}):
            ready = self._request("GET", tasks_ready_endpoint(search_engine), None)
            ready_ids = _ready_task_ids(ready.payload)
            task_ids = {
                task_id
                for task_id, task in pending.items()
                if task.search_engine == search_engine
            }
            listed_ready_ids = task_ids & ready_ids
            task_ids_to_check = sorted(listed_ready_ids) + sorted(
                task_ids - listed_ready_ids
            )
            for task_id in task_ids_to_check:
                task = pending[task_id]
                retrieved = self._request(
                    "GET", task_retrieval_endpoint(search_engine, task_id), None
                )
                if not _result_ready(retrieved.payload):
                    continue
                self._record_retrieval(task, ready, retrieved, now or datetime.now(UTC))
                self._repository.mark_task_retrieved(task.request_id)
                retrieved_ids.append(task_id)
        return retrieved_ids

    def _record_retrieval(
        self,
        task: PendingSERPTask,
        ready: ProviderEnvelope,
        retrieved: ProviderEnvelope,
        collected_at: datetime,
    ) -> None:
        request_id = str(uuid4())
        evidence = RawEvidence(
            source_category="serp",
            provider=task.provider,
            platform_or_engine=task.search_engine,
            run_id=f"serp-retrieval-{uuid4()}",
            request_id=request_id,
            collected_at=collected_at,
            query_id=task.query_id,
            search_target_id=task.search_target_id,
            collection_window=task.collection_window,
            provider_request_id=retrieved.provider_request_id,
            actual_cost_usd=_cost(retrieved.payload),
            attempts=(
                _attempt(request_id, 1, collected_at, "tasks_ready_completed"),
                _attempt(request_id, 2, collected_at, "task_get_completed"),
            ),
            request_payload={
                "tasks_ready": tasks_ready_endpoint(task.search_engine),
                "task_get": task_retrieval_endpoint(task.search_engine, task.task_id),
            },
            response_payload={
                "tasks_ready": ready.payload,
                "retrieval": retrieved.payload,
            },
        )
        raw_result = self._raw_store.write(evidence)
        self._repository.record(evidence, raw_result)


def _task_id(payload: dict[str, Any]) -> str:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        raise ValueError("task post response has no task ID")
    task_id = tasks[0].get("id")
    if not isinstance(task_id, str):
        raise ValueError("task post response has an invalid task ID")
    return task_id


def _assert_task_post_succeeded(payload: dict[str, Any]) -> None:
    """Reject provider task-level errors before they are recorded as pending."""
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        raise ValueError("task post response has no task")
    status_code = tasks[0].get("status_code")
    if not isinstance(status_code, int) or status_code >= 40000:
        message = tasks[0].get("status_message")
        raise ValueError(f"task post failed: {message or status_code}")


def _cost(payload: dict[str, Any]) -> float | None:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        return None
    cost = tasks[0].get("cost")
    return float(cost) if isinstance(cost, int | float) else None


def task_retrieval_endpoint(search_engine: str, task_id: str) -> str:
    """Return the verified advanced result endpoint for a provider task ID."""
    return (
        f"{_API_BASE}/{search_engine.casefold()}/organic/task_get/advanced/{task_id}"
    )


def tasks_ready_endpoint(search_engine: str) -> str:
    """Return the verified endpoint that lists completed standard tasks."""
    return f"{_API_BASE}/{search_engine.casefold()}/organic/tasks_ready"


def _adapter_for(target: SearchTarget):
    try:
        return SERP_ADAPTERS[target.search_engine.casefold()]
    except KeyError as error:
        raise ValueError(
            f"No Standard organic adapter for {target.search_engine}"
        ) from error


def _ready_task_ids(payload: dict[str, Any]) -> set[str]:
    """Extract task IDs only from the documented tasks-ready result list."""
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return set()
    ids: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("result"), list):
            continue
        for ready in task["result"]:
            if isinstance(ready, dict) and isinstance(ready.get("id"), str):
                ids.add(ready["id"])
    return ids


def _result_ready(payload: dict[str, Any]) -> bool:
    """Accept completed results, including the terminal no-results outcome."""
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        return False
    task = tasks[0]
    return task.get("status_code") in {20000, 40102} and isinstance(
        task.get("result"), list
    )


def _attempt(
    request_id: str, number: int, timestamp: datetime, status: str
) -> dict[str, Any]:
    return {
        "attempt_id": f"{request_id}-attempt-{number}",
        "attempt_number": number,
        "started_at": timestamp,
        "ended_at": timestamp,
        "transport_status": status,
    }
