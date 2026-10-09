"""Manually approved, raw-verified evidence copied into a release transaction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import duckdb

EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS presentation.release_evidence (
 release_id VARCHAR NOT NULL, evidence_id VARCHAR NOT NULL,
 metric_id VARCHAR NOT NULL, observation_id VARCHAR NOT NULL,
 source_category VARCHAR NOT NULL, raw_file_hash VARCHAR NOT NULL,
 json_pointer VARCHAR NOT NULL, evidence_kind VARCHAR NOT NULL,
 original_text VARCHAR, url VARCHAR, reviewer VARCHAR NOT NULL,
 approved_at VARCHAR NOT NULL, approval_reason VARCHAR NOT NULL,
 parser_version VARCHAR NOT NULL, registry_version VARCHAR NOT NULL,
 quality_status VARCHAR NOT NULL,
 PRIMARY KEY(release_id, evidence_id)
);
"""


@dataclass(frozen=True)
class ApprovedEvidence:
    """Approval of display content is NOT approval of extraction accuracy/KPIs."""

    evidence_id: str
    metric_id: str
    observation_id: str
    source_category: str
    raw_file: Path
    raw_file_hash: str
    json_pointer: str
    evidence_kind: str
    reviewer: str
    approved_at: datetime
    approval_reason: str
    parser_version: str
    registry_version: str
    quality_status: str = "experimental"


def publish_evidence(
    connection: duckdb.DuckDBPyConnection,
    release_id: str,
    records: tuple[ApprovedEvidence, ...],
) -> None:
    """Validate actual source fields and snapshot lineage, then copy original value.

    No raw text is sent to the consumer on demand. No snippets/URLs generated or
    guessed. Explicit display approval is required for each field. All-or-nothing
    rollback is owned by the release transaction.
    """
    for record in records:
        required = (
            record.evidence_id, record.metric_id, record.observation_id,
            record.reviewer, record.approval_reason, record.parser_version,
            record.registry_version,
        )
        if any(not value.strip() for value in required):
            raise ValueError("evidence approval and lineage fields are required")
        if record.source_category not in {"serp", "llm"}:
            raise ValueError("unsupported evidence source")
        kinds = {"snippet", "answer", "citation_url", "result_url"}
        if record.evidence_kind not in kinds:
            raise ValueError("unsupported evidence kind")
        # Validated extraction needs a separate future benchmark gate, not this API.
        if record.quality_status != "experimental":
            raise ValueError("validated extraction publication is not enabled")
        if record.approved_at.tzinfo is None or record.approved_at.utcoffset() is None:
            raise ValueError("approval timestamp must be timezone-aware")
        row = connection.execute(
            f"SELECT observation_id,raw_file_hash FROM presentation."
            f"release_{record.source_category}_brand_visibility "
            "WHERE release_id=? AND metric_id=?", [release_id, record.metric_id],
        ).fetchall()
        if row != [(record.observation_id, record.raw_file_hash)]:
            raise ValueError("evidence metric/observation/hash does not match snapshot")
        content = record.raw_file.read_bytes()
        if hashlib.sha256(content).hexdigest() != record.raw_file_hash:
            raise ValueError("raw evidence checksum mismatch")
        value = json.loads(content)
        if not record.json_pointer.startswith("/"):
            raise ValueError("an explicit RFC6901 source field pointer is required")
        try:
            for token in record.json_pointer[1:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                value = value[int(token)] if isinstance(value, list) else value[token]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError("source field not found") from error
        if not isinstance(value, str) or not value.strip():
            raise ValueError("original source field must be a nonempty string")
        is_url = record.evidence_kind.endswith("_url")
        if is_url:
            parsed = urlsplit(value)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password):
                raise ValueError("unsafe evidence URL")
        connection.execute(
            "INSERT INTO presentation.release_evidence VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [release_id, record.evidence_id, record.metric_id, record.observation_id,
             record.source_category, record.raw_file_hash, record.json_pointer,
             record.evidence_kind, None if is_url else value, value if is_url else None,
             record.reviewer, record.approved_at.isoformat(), record.approval_reason,
             record.parser_version, record.registry_version, record.quality_status],
        )