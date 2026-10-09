"""Immutable filesystem storage for sanitized requests and complete responses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from geo_research.storage.atomic_files import atomic_write_new
from geo_research.storage.checksums import sha256_bytes, sha256_file

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
_SENSITIVE_KEYS = frozenset(
    {"authorization", "password", "login", "api_key", "apikey", "token", "secret"}
)


class RawEvidenceConflictError(RuntimeError):
    """An existing immutable evidence path is different or incomplete."""


class RawEvidence(BaseModel):
    """Evidence supplied by a future collection layer; this class performs no calls."""

    model_config = ConfigDict(strict=True)

    source_category: Literal["serp", "llm"]
    provider: str = Field(min_length=1)
    platform_or_engine: str = Field(min_length=1)
    model_name: str | None = None
    run_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    collected_at: datetime
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    query_id: str | None = None
    search_target_id: str | None = None
    collection_window: str | None = None
    request_hash: str | None = None
    deduplication_key: str | None = None
    estimated_cost_usd: float | None = None
    provider_request_id: str | None = None
    actual_cost_usd: float | None = None
    attempts: tuple[dict[str, Any], ...] = ()
    request_status: str = "completed"
    request_content_type: str = "application/json"
    response_content_type: str = "application/json"

    @field_validator("collected_at")
    @classmethod
    def collected_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        """Reject naive timestamps before they can affect an evidence path."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class RawFile:
    """Finalized immutable artifact metadata."""

    path: Path
    sha256: str
    byte_size: int
    content_type: str


@dataclass(frozen=True, slots=True)
class RawWriteResult:
    """Finalized raw evidence directory and its request/response artifacts."""

    directory: Path
    request: RawFile
    response: RawFile
    metadata: RawFile


@dataclass(frozen=True, slots=True)
class RawIntegrityResult:
    """Integrity result that preserves all discovered problems."""

    valid: bool
    problems: tuple[str, ...]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode(
        "utf-8"
    )


def sanitize_payload(value: object) -> object:
    """Remove credential-bearing keys and sensitive URL parameter values recursively."""
    if isinstance(value, dict):
        return {
            key: sanitize_payload(item)
            for key, item in value.items()
            if key.casefold() not in _SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return re.sub(
            r"(?i)([?&](?:api[_-]?key|token|access_token|password|secret)=)[^&#\s]*",
            r"\1[REDACTED]",
            value,
        )
    return value


class RawStore:
    """Writes immutable raw artifacts below one configured raw root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, evidence: RawEvidence) -> RawWriteResult:
        """Write evidence once or return an existing byte-identical immutable write."""
        directory = self._directory_for(evidence)
        request_content = _canonical_json(sanitize_payload(evidence.request_payload))
        response_content = _canonical_json(evidence.response_payload)
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return self._existing_or_conflict(
                directory, request_content, response_content
            )
        try:
            request = self._write_file(
                directory / "request.json",
                request_content,
                evidence.request_content_type,
            )
            response = self._write_file(
                directory / "response.json",
                response_content,
                evidence.response_content_type,
            )
            metadata_content = _canonical_json(
                {
                    "source_category": evidence.source_category,
                    "provider": evidence.provider,
                    "platform_or_engine": evidence.platform_or_engine,
                    "run_id": evidence.run_id,
                    "request_id": evidence.request_id,
                    "collected_at": evidence.collected_at.isoformat(),
                    "files": {
                        "request.json": self._file_metadata(request),
                        "response.json": self._file_metadata(response),
                    },
                }
            )
            metadata = self._write_file(
                directory / "metadata.json", metadata_content, "application/json"
            )
        except Exception:
            raise
        return RawWriteResult(directory, request, response, metadata)

    def verify(self, directory: Path) -> RawIntegrityResult:
        """Verify expected files, sizes, and SHA-256 hashes.

        This operation does not alter evidence.
        """
        metadata_path = directory / "metadata.json"
        problems: list[str] = []
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return RawIntegrityResult(False, ("missing or invalid metadata.json",))
        files = metadata.get("files")
        if not isinstance(files, dict):
            return RawIntegrityResult(False, ("metadata has no file manifest",))
        for filename in ("request.json", "response.json"):
            expected = files.get(filename)
            path = directory / filename
            if not isinstance(expected, dict) or not path.is_file():
                problems.append(f"missing {filename}")
                continue
            if path.stat().st_size != expected.get("byte_size"):
                problems.append(f"size mismatch for {filename}")
            if sha256_file(path) != expected.get("sha256"):
                problems.append(f"checksum mismatch for {filename}")
        return RawIntegrityResult(not problems, tuple(problems))

    def find_orphans(self) -> list[Path]:
        """Find evidence directories with temporary files or incomplete manifests."""
        if not self.root.exists():
            return []
        candidates: set[Path] = set()
        for path in self.root.rglob("*"):
            if path.is_file() and (
                path.name.endswith(".tmp")
                or path.name in {"request.json", "response.json"}
            ):
                parent = path.parent
                if (
                    path.name.endswith(".tmp")
                    or not (parent / "metadata.json").is_file()
                ):
                    candidates.add(parent)
        return sorted(candidates)

    def evidence_directories(self) -> set[Path]:
        """Return completed evidence directories.

        Incomplete and orphaned paths are excluded.
        """
        if not self.root.exists():
            return set()
        return {
            path.parent
            for path in self.root.rglob("metadata.json")
            if self.verify(path.parent).valid
        }

    def _directory_for(self, evidence: RawEvidence) -> Path:
        segments = (
            evidence.source_category,
            evidence.provider,
            evidence.platform_or_engine,
            evidence.run_id,
            evidence.request_id,
        )
        if not all(_SAFE_SEGMENT.fullmatch(segment) for segment in segments):
            raise ValueError("raw path dimensions must be filesystem-safe segments")
        timestamp = evidence.collected_at.astimezone(UTC).date()
        return (
            self.root
            / evidence.source_category
            / evidence.provider
            / evidence.platform_or_engine
            / f"{timestamp:%Y}"
            / f"{timestamp:%m}"
            / f"{timestamp:%d}"
            / evidence.run_id
            / evidence.request_id
        )

    def _write_file(self, path: Path, content: bytes, content_type: str) -> RawFile:
        atomic_write_new(path, content)
        return RawFile(path, sha256_bytes(content), len(content), content_type)

    def _existing_or_conflict(
        self, directory: Path, request_content: bytes, response_content: bytes
    ) -> RawWriteResult:
        integrity = self.verify(directory)
        if not integrity.valid:
            raise RawEvidenceConflictError(
                f"Existing raw evidence is incomplete: {directory}"
            )
        request_path = directory / "request.json"
        response_path = directory / "response.json"
        if (
            request_path.read_bytes() != request_content
            or response_path.read_bytes() != response_content
        ):
            raise RawEvidenceConflictError(
                f"Conflicting immutable raw evidence: {directory}"
            )
        metadata_path = directory / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        manifest = cast(dict[str, dict[str, str | int]], metadata["files"])
        return RawWriteResult(
            directory,
            self._raw_file_from_metadata(request_path, manifest["request.json"]),
            self._raw_file_from_metadata(response_path, manifest["response.json"]),
            RawFile(
                metadata_path,
                sha256_file(metadata_path),
                metadata_path.stat().st_size,
                "application/json",
            ),
        )

    @staticmethod
    def _file_metadata(raw_file: RawFile) -> dict[str, str | int]:
        return {
            "sha256": raw_file.sha256,
            "byte_size": raw_file.byte_size,
            "content_type": raw_file.content_type,
        }

    @staticmethod
    def _raw_file_from_metadata(path: Path, metadata: dict[str, str | int]) -> RawFile:
        return RawFile(
            path=path,
            sha256=str(metadata["sha256"]),
            byte_size=int(metadata["byte_size"]),
            content_type=str(metadata["content_type"]),
        )
