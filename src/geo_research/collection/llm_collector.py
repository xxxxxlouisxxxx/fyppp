"""Controlled DataForSEO ChatGPT and Gemini LLM Scraper task collection."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from geo_research.collection.deduplication import SuccessfulDeduplicator
from geo_research.collection.identity import llm_request_hash
from geo_research.connectors.dataforseo.envelope import ProviderEnvelope
from geo_research.domain.assignments import PromptTargetAssignment
from geo_research.domain.llm import LLMPrompt, LLMTarget
from geo_research.registries.validators import _parse_registry, validate_registries
from geo_research.storage.raw_store import RawEvidence, RawStore
from geo_research.storage.repositories import PendingLLMTask, RawEvidenceRepository

_LLM_SCRAPER_ENDPOINTS = {
    "chat_gpt": "https://api.dataforseo.com/v3/ai_optimization/chat_gpt/llm_scraper",
    "gemini": "https://api.dataforseo.com/v3/ai_optimization/gemini/llm_scraper",
}

ProviderRequest = Callable[
    [str, str, Mapping[str, object] | Sequence[Mapping[str, object]] | None],
    ProviderEnvelope,
]


@dataclass(frozen=True, slots=True)
class LLMPlan:
    prompt_id: str
    target_id: str
    provider: str
    endpoint: str | None
    request_hash: str
    deduplication_key: str
    estimated_cost_usd: float | None
    capability_verified: bool
    safe_payload: dict[str, Any]
    expected_raw_path: str


@dataclass(frozen=True, slots=True)
class LLMCollectionAssignment:
    """One resolved, active CSV assignment eligible for task posting."""

    prompt: LLMPrompt
    target: LLMTarget


@dataclass(frozen=True, slots=True)
class LLMCollectionResult:
    """Non-secret result of one submitted LLM Scraper task."""

    request_id: str
    task_id: str


def load_active_chat_gpt_assignments(directory: str) -> list[LLMCollectionAssignment]:
    """Load only validated, active DataForSEO ChatGPT task-post assignments."""
    return [
        assignment
        for assignment in load_active_llm_scraper_assignments(directory)
        if assignment.target.platform == "chat_gpt"
    ]


def load_active_llm_scraper_assignments(
    directory: str,
) -> list[LLMCollectionAssignment]:
    """Load validated active assignments for supported LLM Scraper platforms."""
    registry_directory = Path(directory)
    validate_registries(registry_directory)
    prompts = cast(
        list[LLMPrompt],
        _parse_registry(registry_directory, "llm_prompts.csv", LLMPrompt, "prompt_id"),
    )
    targets = cast(
        list[LLMTarget],
        _parse_registry(
            registry_directory,
            "llm_targets.csv",
            LLMTarget,
            "llm_target_id",
        ),
    )
    assignments = cast(
        list[PromptTargetAssignment],
        _parse_registry(
            registry_directory,
            "prompt_target_assignments.csv",
            PromptTargetAssignment,
            "assignment_id",
        ),
    )
    prompt_by_id = {prompt.prompt_id: prompt for prompt in prompts}
    target_by_id = {target.llm_target_id: target for target in targets}
    return [
        LLMCollectionAssignment(prompt_by_id[assignment.prompt_id], target)
        for assignment in assignments
        if assignment.active
        and prompt_by_id[assignment.prompt_id].active
        and (target := target_by_id[assignment.llm_target_id]).active
        and target.provider == "dataforseo"
        and target.platform in _LLM_SCRAPER_ENDPOINTS
        and target.endpoint_name == _task_post_endpoint_name(target.platform)
    ]


class LLMCollector:
    """Posts tasks and retrieves ready results without retries or polling."""

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
        assignment: LLMCollectionAssignment,
        *,
        run_id: str,
        collection_window: str,
        estimated_cost_usd: float,
        now: datetime | None = None,
    ) -> LLMCollectionResult:
        """Post exactly one documented task request and commit its evidence."""
        request_id = str(uuid4())
        collected_at = now or datetime.now(UTC)
        task_post_endpoint = _task_post_endpoint(assignment.target.platform)
        options: dict[str, Any] = {}
        payload_item: dict[str, Any] = {
            "keyword": assignment.prompt.prompt_text,
            "location_code": int(assignment.target.location_code),
            "language_code": assignment.target.language_code,
            "tag": _task_tag(
                collection_window,
                assignment.prompt.prompt_id,
                assignment.target.llm_target_id,
            ),
        }
        if assignment.target.platform == "chat_gpt":
            payload_item["force_web_search"] = True
            options["force_web_search"] = True
        payload = [payload_item]
        request_hash = llm_request_hash(
            provider=assignment.target.provider,
            platform=assignment.target.platform,
            model_name=assignment.target.model_name,
            endpoint=task_post_endpoint,
            prompt_text=assignment.prompt.prompt_text,
            location=assignment.target.location_code,
            language=assignment.target.language_code,
            options=options,
            adapter_version=f"{assignment.target.platform}-llm-scraper-task-v1",
            capability_evidence_version="dataforseo-2026-09-27",
        )
        response = self._request("POST", task_post_endpoint, payload)
        task_id = _task_id(response.payload)
        evidence = RawEvidence(
            source_category="llm",
            provider=assignment.target.provider,
            platform_or_engine=assignment.target.platform,
            model_name=assignment.target.model_name,
            run_id=run_id,
            request_id=request_id,
            collected_at=collected_at,
            query_id=str(assignment.prompt.prompt_id),
            search_target_id=str(assignment.target.llm_target_id),
            collection_window=collection_window,
            request_hash=request_hash,
            deduplication_key=SuccessfulDeduplicator().key(
                "llm",
                assignment.target.provider,
                task_post_endpoint,
                request_hash,
                collection_window,
            ),
            estimated_cost_usd=estimated_cost_usd,
            provider_request_id=response.provider_request_id,
            actual_cost_usd=_cost(response.payload),
            request_status="submitted_pending_result",
            attempts=(_attempt(request_id, 1, collected_at, "task_post_completed"),),
            request_payload={"post": payload},
            response_payload={"post": response.payload},
        )
        raw_result = self._raw_store.write(evidence)
        self._repository.record(evidence, raw_result)
        return LLMCollectionResult(request_id, task_id)

    def retrieve_ready(self, *, now: datetime | None = None) -> list[str]:
        """Retrieve ready tasks, falling back to direct checks for omitted IDs."""
        pending = {task.task_id: task for task in self._repository.pending_llm_tasks()}
        if not pending:
            return []
        retrieved_ids: list[str] = []
        for platform in sorted({task.platform for task in pending.values()}):
            ready = self._request("GET", _tasks_ready_endpoint(platform), None)
            ready_ids = _ready_task_ids(ready.payload)
            task_ids = {
                task_id
                for task_id, task in pending.items()
                if task.platform == platform
            }
            listed_ready_ids = task_ids & ready_ids
            task_ids_to_check = sorted(listed_ready_ids) + sorted(
                task_ids - listed_ready_ids
            )
            for task_id in task_ids_to_check:
                task = pending[task_id]
                retrieved = self._request(
                    "GET", _task_get_advanced_endpoint(platform, task_id), None
                )
                if not _result_ready(retrieved.payload):
                    continue
                self._record_retrieval(task, ready, retrieved, now or datetime.now(UTC))
                self._repository.mark_task_retrieved(task.request_id)
                retrieved_ids.append(task_id)
        return retrieved_ids

    def _record_retrieval(
        self,
        task: PendingLLMTask,
        ready: ProviderEnvelope,
        retrieved: ProviderEnvelope,
        collected_at: datetime,
    ) -> None:
        request_id = str(uuid4())
        evidence = RawEvidence(
            source_category="llm",
            provider=task.provider,
            platform_or_engine=task.platform,
            model_name=task.model_name,
            run_id=f"llm-retrieval-{uuid4()}",
            request_id=request_id,
            collected_at=collected_at,
            query_id=task.prompt_id,
            search_target_id=task.llm_target_id,
            collection_window=task.collection_window,
            provider_request_id=retrieved.provider_request_id,
            actual_cost_usd=_cost(retrieved.payload),
            attempts=(
                _attempt(request_id, 1, collected_at, "tasks_ready_completed"),
                _attempt(request_id, 2, collected_at, "task_get_completed"),
            ),
            request_payload={
                "tasks_ready": _tasks_ready_endpoint(task.platform),
                "task_get": _task_get_advanced_endpoint(task.platform, task.task_id),
            },
            response_payload={
                "tasks_ready": ready.payload,
                "retrieval": retrieved.payload,
            },
        )
        raw_result = self._raw_store.write(evidence)
        self._repository.record(evidence, raw_result)


def _task_tag(collection_window: str, prompt_id: str, target_id: str) -> str:
    """Build a provider-reconcilable LLM task identity."""
    tag = f"llm:{collection_window}:{prompt_id}:{target_id}"
    if len(tag) > 255:
        raise ValueError("LLM task tag exceeds the provider's 255-character limit")
    return tag


def _task_post_endpoint(platform: str) -> str:
    return f"{_platform_endpoint(platform)}/task_post"


def _task_post_endpoint_name(platform: str) -> str:
    return f"ai_optimization/{platform}/llm_scraper/task_post"


def _tasks_ready_endpoint(platform: str) -> str:
    return f"{_platform_endpoint(platform)}/tasks_ready"


def _task_get_advanced_endpoint(platform: str, task_id: str) -> str:
    return f"{_platform_endpoint(platform)}/task_get/advanced/{task_id}"


def _platform_endpoint(platform: str) -> str:
    try:
        return _LLM_SCRAPER_ENDPOINTS[platform.casefold()]
    except KeyError as error:
        raise ValueError(f"Unsupported LLM Scraper platform: {platform}") from error


def _cost(payload: dict[str, Any]) -> float | None:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        return None
    cost = tasks[0].get("cost")
    return float(cost) if isinstance(cost, int | float) else None


def _task_id(payload: dict[str, Any]) -> str:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        raise ValueError("task post response has no task ID")
    task_id = tasks[0].get("id")
    if not isinstance(task_id, str):
        raise ValueError("task post response has an invalid task ID")
    return task_id


def _ready_task_ids(payload: dict[str, Any]) -> set[str]:
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
    tasks = payload.get("tasks")
    return (
        isinstance(tasks, list)
        and bool(tasks)
        and isinstance(tasks[0], dict)
        and tasks[0].get("status_code") == 20000
        and isinstance(tasks[0].get("result"), list)
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
