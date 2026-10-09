"""Register checksum-verified pre-existing Raw evidence in Bronze metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from geo_research.storage.duckdb import DuckDBStore
from geo_research.storage.raw_store import (
    RawEvidence,
    RawFile,
    RawStore,
    RawWriteResult,
)
from geo_research.storage.repositories import RawEvidenceRepository


@dataclass(frozen=True, slots=True)
class RawRegistrationReport:
    """Counts and invalid artifact directories from one Raw registration pass."""

    registered: int
    already_registered: int
    invalid_directories: tuple[str, ...]


def register_verified_raw_evidence(
    database: DuckDBStore,
    raw_root: Path,
) -> RawRegistrationReport:
    """Record metadata for valid Raw artifacts without changing their contents.

    Existing request identifiers are left untouched. Raw manifests do not contain
    registry mappings, so query/prompt identities remain null rather than inferred.
    """
    database.initialize()
    raw_store = RawStore(raw_root)
    repository = RawEvidenceRepository(database, raw_store)
    invalid_directories: list[str] = []
    registered = 0
    already_registered = 0
    records: list[tuple[RawEvidence, RawWriteResult]] = []
    with database.transaction() as connection:
        registered_request_ids = {
            str(row[0])
            for row in connection.execute(
                "SELECT request_id FROM bronze.api_requests"
            ).fetchall()
        }

    for directory in raw_store.evidence_directories():
        metadata = _read_metadata(directory)
        if metadata is None:
            invalid_directories.append(str(directory))
            continue
        request_id = metadata.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            invalid_directories.append(str(directory))
            continue
        if request_id in registered_request_ids:
            already_registered += 1
            continue
        try:
            evidence, result = _evidence_from_artifacts(raw_root, directory, metadata)
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            invalid_directories.append(str(directory))
            continue
        records.append((evidence, result))
        registered_request_ids.add(request_id)
        registered += 1

    repository.record_many(records)

    return RawRegistrationReport(
        registered=registered,
        already_registered=already_registered,
        invalid_directories=tuple(sorted(invalid_directories)),
    )
def _read_metadata(directory: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _evidence_from_artifacts(
    raw_root: Path,
    directory: Path,
    metadata: dict[str, Any],
) -> tuple[RawEvidence, RawWriteResult]:
    source_category = _required_text(metadata, "source_category")
    if source_category not in {"serp", "llm"}:
        raise ValueError("unsupported source category")
    collected_at = datetime.fromisoformat(_required_text(metadata, "collected_at"))
    request_payload = _read_json_object(directory / "request.json")
    response_payload = _read_json_object(directory / "response.json")
    files = metadata.get("files")
    if not isinstance(files, dict):
        raise ValueError("missing file metadata")
    request_file = _raw_file(directory / "request.json", files.get("request.json"))
    response_file = _raw_file(directory / "response.json", files.get("response.json"))
    metadata_file = RawFile(
        path=directory / "metadata.json",
        sha256="manifest-not-persisted-in-bronze",
        byte_size=(directory / "metadata.json").stat().st_size,
        content_type="application/json",
    )
    platform_or_engine = _required_text(metadata, "platform_or_engine")
    evidence = RawEvidence(
        source_category=source_category,
        provider=_required_text(metadata, "provider"),
        platform_or_engine=platform_or_engine,
        run_id=_required_text(metadata, "run_id"),
        request_id=_required_text(metadata, "request_id"),
        collected_at=collected_at,
        request_payload=request_payload,
        response_payload=response_payload,
        request_status="completed",
    )
    return evidence, RawWriteResult(
        directory, request_file, response_file, metadata_file,
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("artifact must contain a JSON object")
    return loaded


def _raw_file(path: Path, metadata: object) -> RawFile:
    if not isinstance(metadata, dict):
        raise ValueError("missing artifact file metadata")
    sha256 = metadata.get("sha256")
    byte_size = metadata.get("byte_size")
    content_type = metadata.get("content_type")
    if not isinstance(sha256, str) or not isinstance(byte_size, int):
        raise ValueError("invalid artifact file metadata")
    if not isinstance(content_type, str):
        raise ValueError("invalid artifact content type")
    return RawFile(path, sha256, byte_size, content_type)


def _required_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {key}")
    return value.strip()