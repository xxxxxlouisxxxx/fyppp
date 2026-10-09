"""Normalize raw DataForSEO LLM response payloads into a staged record."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def transform_llm_raw_file(path: str | Path) -> dict[str, Any]:
    """Load a raw JSON file and return a staged LLM observation payload."""
    raw_path = Path(path)
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    return transform_llm_raw_payload(payload)


def transform_llm_raw_payload(payload: object) -> dict[str, Any]:
    """Flatten a DataForSEO raw LLM response into a normalized staging record."""
    if not isinstance(payload, Mapping):
        raise ValueError("raw LLM payload must be a JSON object")

    retrieval = payload.get("retrieval")
    if not isinstance(retrieval, Mapping):
        raise ValueError("raw LLM payload is missing 'retrieval' block")

    tasks = retrieval.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("raw LLM payload is missing retrieval tasks")
    if len(tasks) != 1:
        raise ValueError("unsupported multiple LLM tasks; do not truncate")

    task = tasks[0]
    if not isinstance(task, Mapping):
        raise ValueError("first retrieval task is malformed")

    task_data = task.get("data")
    if not isinstance(task_data, Mapping):
        task_data = {}

    result_list = task.get("result")
    if not isinstance(result_list, list) or not result_list:
        raise ValueError("raw LLM payload contains no result items")
    if len(result_list) != 1:
        raise ValueError("unsupported multiple LLM results; do not truncate")

    result = result_list[0]
    if not isinstance(result, Mapping):
        raise ValueError("first result entry is malformed")

    items = result.get("items", [])
    if not isinstance(items, Sequence):
        items = []

    normalized_items: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        original_text = item.get("original_text") or item.get("markdown") or ""
        normalized_item = {
            "index": index,
            "item_type": item.get("type", "unknown"),
            "rank_group": item.get("rank_group"),
            "rank_absolute": item.get("rank_absolute"),
            "text": str(original_text).strip(),
            "markdown": item.get("markdown"),
            "raw_item": dict(item),
            "json_path": f"$.retrieval.tasks[0].result[0].items[{index}]",
            "result_sources": result.get("sources"),
            "sources": [],
        }
        source_entries = item.get("sources")
        if isinstance(source_entries, Sequence):
            for source in source_entries:
                if not isinstance(source, Mapping):
                    continue
                citation = {
                    "domain": source.get("domain"),
                    "source_name": source.get("source_name"),
                    "title": source.get("title"),
                    "url": source.get("url"),
                    "snippet": source.get("snippet"),
                    "markdown": source.get("markdown"),
                    "type": source.get("type"),
                }
                normalized_item["sources"].append(citation)
                citations.append(citation)
        normalized_items.append(normalized_item)

    return {
        "provider": "dataforseo",
        "platform": str(task_data.get("se", "unknown")).lower(),
        "model": result.get("model") or task_data.get("model") or "unknown",
        "query": str(task_data.get("keyword") or result.get("keyword") or "").strip(),
        "task_id": task.get("id"),
        "status_code": retrieval.get("status_code", task.get("status_code")),
        "cost": retrieval.get("cost", task.get("cost")),
        "language_code": str(
            task_data.get("language_code") or result.get("language_code") or ""
        ).strip(),
        "location_code": task_data.get("location_code") or result.get("location_code"),
        "items_count": len(normalized_items),
        "result_count": len(normalized_items),
        "response_text": result.get("markdown") or "\n\n".join(
            item.get("text") for item in normalized_items if item.get("text")
        ),
        "items": normalized_items,
        "citations": citations,
    }
