# ruff: noqa: E501, I001
"""Offline, exhaustive raw audit and isolated Bronze/Silver reconstruction.

No APIs, raw writes, fixture seeds, publication, or dbt invocation. Existing
warehouses are opened read-only and only checksum-matched request provenance is
eligible. Run dbt separately against the returned *new* database, with fixture
bootstrap disabled. Unresolved registry identities stay null in Bronze; the
non-null legacy SERP observation key uses an explicitly labelled raw request.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import duckdb  # noqa: E402

from geo_research.parsers.serp.contracts import (  # noqa: E402, I001
    SearchObservation, SERPItem, SERPParseResult, SERPParsingQuarantine,
)
from geo_research.parsers.serp.features import (  # noqa: E402
    OrganicResult, SERPFeatureResult, parse_serp_features,
)
from geo_research.parsers.serp.service import (  # noqa: E402
    SERPParseInput, parse_serp_response, supported_serp_engines,
)
from geo_research.storage.duckdb import DuckDBStore  # noqa: E402
from geo_research.storage.raw_store import (  # noqa: E402
    RawEvidence, RawFile, RawStore, RawWriteResult,
)
from geo_research.storage.repositories import (  # noqa: E402
    RawEvidenceRepository, SilverLLMObservation, SilverLLMRepository,
    SilverSERPFeatureRepository, SilverSERPRepository,
)
from geo_research.transforms.llm_raw import transform_llm_raw_payload  # noqa: E402
from geo_research.transforms.response_evidence import enrich_database  # noqa: E402
from geo_research.transforms.feature_evidence import export_candidate_review  # noqa: E402


def dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def identifier(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, value))


def _json_bytes(content: bytes) -> Any:
    def no_constant(value: str) -> None:
        raise ValueError(f"non-JSON constant: {value}")

    return json.loads(content.decode("utf-8"), parse_constant=no_constant)


def audit_raw(raw_root: Path, raw_date: date | None = None) -> list[dict[str, Any]]:
    """Inventory every JSON, including auxiliaries and incomplete triples."""
    rows: list[dict[str, Any]] = []
    by_directory: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    for category in ("serp", "llm"):
        for path in sorted((raw_root / category).rglob("*.json")):
            # Scope by the preserved folder date, not provider result datetime.
            if raw_date is not None and path.relative_to(raw_root).parts[3:6] != tuple(raw_date.strftime("%Y/%m/%d").split("/")):
                continue
            role = {"metadata.json": "metadata", "request.json": "request",
                    "response.json": "response"}.get(path.name, "auxiliary")
            row = {"path": str(path.relative_to(raw_root)), "category": category,
                   "role": role, "byte_size": None, "sha256": None,
                   "json_valid": False, "json_type": None, "json_error": None,
                   "request_id": None, "engine_or_platform": None,
                   "collected_at": None, "triple_valid": False,
                   "integrity_problems": [], "disposition": "unreviewed"}
            try:
                content = path.read_bytes()
                row.update(byte_size=len(content), sha256=hashlib.sha256(content).hexdigest())
                value = _json_bytes(content)
                row.update(json_valid=True, json_type=type(value).__name__)
            except (OSError, UnicodeError, ValueError) as exc:
                row["json_error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            by_directory[path.parent].append(row)
    for directory, members in by_directory.items():
        indexed = {row["role"]: row for row in members if row["role"] != "auxiliary"}
        problems = []
        for role in ("metadata", "request", "response"):
            if role not in indexed:
                problems.append(f"missing {role}.json")
            elif not indexed[role]["json_valid"]:
                problems.append(f"invalid JSON {role}.json")
            elif indexed[role]["json_type"] != "dict":
                problems.append(f"non-object {role}.json")
        metadata: dict[str, Any] = {}
        if "metadata" in indexed and indexed["metadata"]["json_valid"]:
            loaded = _json_bytes((directory / "metadata.json").read_bytes())
            if isinstance(loaded, dict):
                metadata = loaded
        files = metadata.get("files")
        if not isinstance(files, dict):
            problems.append("metadata has no file manifest")
            files = {}
        for role in ("request", "response"):
            expected = files.get(f"{role}.json")
            actual = indexed.get(role)
            if not isinstance(expected, dict):
                problems.append(f"missing file manifest {role}.json")
            elif actual:
                if actual["sha256"] != expected.get("sha256"):
                    problems.append(f"checksum mismatch for {role}.json")
                if actual["byte_size"] != expected.get("byte_size"):
                    problems.append(f"size mismatch for {role}.json")
                if not isinstance(expected.get("content_type"), str):
                    problems.append(f"missing content_type for {role}.json")
        for key in ("request_id", "run_id", "provider", "platform_or_engine", "collected_at"):
            if not isinstance(metadata.get(key), str) or not metadata[key]:
                problems.append(f"missing metadata {key}")
        if metadata.get("source_category") != members[0]["category"]:
            problems.append("source_category/path mismatch")
        try:
            collected = datetime.fromisoformat(metadata.get("collected_at", ""))
            if collected.utcoffset() is None:
                problems.append("collected_at is not timezone aware")
        except (TypeError, ValueError):
            problems.append("invalid collected_at")
        for row in members:
            row.update(request_id=metadata.get("request_id"),
                       engine_or_platform=metadata.get("platform_or_engine"),
                       collected_at=metadata.get("collected_at"),
                       triple_valid=not problems, integrity_problems=problems.copy())
            if row["role"] == "auxiliary":
                row["disposition"] = "auxiliary_not_result" if row["json_valid"] else "quarantined_auxiliary"
                canonical = directory / "response.json"
                if row["json_valid"] and canonical.is_file():
                    try:
                        if _json_bytes((raw_root / row["path"]).read_bytes()) == _json_bytes(canonical.read_bytes()):
                            row["disposition"] = "duplicate_response_representation"
                    except (OSError, UnicodeError, ValueError):
                        pass
            elif problems:
                row["disposition"] = "quarantined_integrity"
            elif row["role"] != "response":
                row["disposition"] = f"{row['role']}_evidence_not_result"
            else:
                row["disposition"] = "verified_response_candidate"
    return rows


def _rows(connection: Any, sql: str) -> list[dict[str, Any]]:
    result = connection.execute(sql)
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def read_provenance(paths: list[Path]) -> tuple[dict[tuple[str, str], list[dict]], dict, list]:
    """Require BOTH request ID and response SHA, never suffix/topic matching."""
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    registries: dict[str, dict[str, list[dict]]] = {}
    reports = []
    for path in paths:
        report = {"path": str(path), "read_only": True, "matched_candidates": 0, "error": None}
        try:
            with duckdb.connect(str(path), read_only=True) as connection:
                connection.execute("SET TimeZone='UTC'")
                connection.execute("BEGIN TRANSACTION")
                candidates = _rows(connection, "SELECT r.*, f.sha256 AS response_sha256 "
                                   "FROM bronze.api_requests r JOIN bronze.raw_files f "
                                   "USING(request_id) WHERE f.artifact_type='response'")
                for row in candidates:
                    row["provenance_database"] = str(path)
                    index[(row["request_id"], row["response_sha256"])].append(row)
                report["matched_candidates"] = len(candidates)
                tables = connection.execute("SELECT table_name FROM information_schema.tables "
                                            "WHERE table_schema='bronze' AND table_name LIKE '%registry'").fetchall()
                registries[str(path)] = {
                    table: _rows(connection, f'SELECT * FROM bronze."{table}"')
                    for (table,) in tables
                }
                connection.execute("COMMIT")
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
        reports.append(report)
    return index, registries, reports


def reconcile_context(metadata: dict, sha: str, index: dict) -> tuple[dict, list, list]:
    candidates = index.get((metadata["request_id"], sha), [])
    context = {}
    conflicts = []
    for field in ("query_id", "search_target_id", "collection_window", "model_name",
                  "request_hash", "deduplication_key"):
        values = {str(row[field]) for row in candidates if row.get(field) not in (None, "")}
        if metadata.get(field) not in (None, ""):
            values.add(str(metadata[field]))
        if len(values) == 1:
            context[field] = values.pop()
        elif len(values) > 1:
            conflicts.append(field)
    return context, sorted({row["provenance_database"] for row in candidates}), conflicts


def envelope(payload: dict) -> tuple[str, dict]:
    for key in ("retrieval", "live_advanced", "get", "post"):
        if isinstance(payload.get(key), dict) and "tasks" in payload[key]:
            return key, copy.deepcopy(payload[key])
    if "tasks" in payload:
        return "direct", copy.deepcopy(payload)
    raise ValueError("unsupported envelope: no known tasks contract")


def provider_status(block: dict) -> tuple[str, dict, dict]:
    tasks = block.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise ValueError("unsupported/malformed task count (expected one task per response)")
    task = tasks[0]
    data = task.get("data") if isinstance(task.get("data"), dict) else {}
    codes = [block.get("status_code"), task.get("status_code")]
    if any(isinstance(code, int) and code >= 40000 for code in codes):
        return "provider_error", task, data
    if task.get("status_code") in (20100, 20101, 20102, 20103, 20104):
        return "pending", task, data
    results = task.get("result")
    if results is None:
        raise ValueError("successful/unknown task without result or pending status")
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        raise ValueError("malformed result contract")
    return "available" if results else "no_results", task, data


class _LocalDatabase:
    """Existing repository API, one connection, explicit per-request transaction."""

    def __init__(self, connection: Any):
        self.connection = connection

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN TRANSACTION")
        try:
            yield self.connection
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise


def seed_registries(connection: Any, directory: Path, provenance: dict,
                    used: dict[str, set[str]], now: datetime) -> dict:
    """Configured CSV is authoritative; DB fallback needs matched raw provenance."""
    if (directory / "comparisons.csv").exists():
        from geo_research.registries.validators import load_comparisons

        load_comparisons(directory)
    # DDL only. Deliberately never execute the dbt fixture macro or its INSERTs.
    for table, columns in (
        ("brand_registry", "brand_id VARCHAR PRIMARY KEY, canonical_name VARCHAR NOT NULL, "
         "ownership_type VARCHAR NOT NULL, market VARCHAR NOT NULL, language VARCHAR NOT NULL, "
         "effective_start_date DATE NOT NULL, effective_end_date DATE, active BOOLEAN NOT NULL, recorded_at TIMESTAMPTZ NOT NULL"),
        ("brand_alias_registry", "brand_alias_id VARCHAR PRIMARY KEY, brand_id VARCHAR NOT NULL, alias_text VARCHAR NOT NULL, "
         "market VARCHAR NOT NULL, language VARCHAR NOT NULL, effective_start_date DATE NOT NULL, effective_end_date DATE, recorded_at TIMESTAMPTZ NOT NULL"),
        ("brand_domain_registry", "brand_domain_id VARCHAR PRIMARY KEY, brand_id VARCHAR NOT NULL, domain VARCHAR NOT NULL, "
         "market VARCHAR NOT NULL, language VARCHAR NOT NULL, effective_start_date DATE NOT NULL, effective_end_date DATE, recorded_at TIMESTAMPTZ NOT NULL"),
    ):
        connection.execute(f"CREATE TABLE IF NOT EXISTS bronze.{table} ({columns})")
    report: dict[str, Any] = {"counts": {}, "excluded": [], "conflicts": [], "sources": [],
        "notes": ["CSV prompt_group absent: stored blank (unknown), full CSV preserved in meta.registry_csv.",
                  "No topic, query/prompt suffix, or date-based comparison inference. "
                  "Explicit user-approved comparisons CSV is authoritative; approval "
                  "metadata is preserved in meta.registry_csv."]}
    connection.execute("CREATE TABLE meta.registry_csv (registry_name VARCHAR, row_json VARCHAR)")
    names = {"brands": "brand_registry", "brand_aliases": "brand_alias_registry",
             "brand_domains": "brand_domain_registry", "queries": "query_registry",
             "search_targets": "search_target_registry", "llm_prompts": "llm_prompt_registry",
             "llm_targets": "llm_target_registry", "comparisons": "comparison_registry"}
    accepted: dict[str, dict[str, dict]] = {table: {} for table in names.values()}
    for filename, table in names.items():
        path = directory / f"{filename}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
        report["sources"].append(str(path))
        for row in records:
            connection.execute("INSERT INTO meta.registry_csv VALUES (?, ?)", [filename, dump(row)])
            key = next(iter(row))
            accepted[table][row[key]] = dict(row)
    # Only non-fixture registry rows from databases matching this run's raw files.
    db_candidates: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path, request_ids in used.items():
        regs = provenance.get(path, {})
        for table in names.values():
            for row in regs.get(table, []):
                key = next(iter(row))
                if table in ("query_registry", "llm_prompt_registry", "search_target_registry", "llm_target_registry") and row[key] not in request_ids:
                    continue
                if table == "comparison_registry" and (
                    row.get("query_id") not in request_ids
                    or row.get("prompt_id") not in request_ids
                ):
                    continue
                if "sanitized" in dump(row).casefold():
                    continue
                db_candidates[(table, str(row[key]))].append(row)
    for (table, key), rows in db_candidates.items():
        if key in accepted[table]:
            continue
        if len({dump({k: v for k, v in row.items() if k != "recorded_at"}) for row in rows}) == 1:
            accepted[table][key] = rows[0]
        else:
            report["conflicts"].append({"table": table, "id": key})
    brand_ids = set()
    for table in names.values():
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info('bronze.{table}')").fetchall()]
        count = 0
        for key, original in accepted[table].items():
            row = original.copy()
            reason = None
            if table == "brand_registry" and (row.get("ownership_type") == "TO_BE_VERIFIED" or "example" in str(row.get("canonical_name", "")).casefold()):
                reason = "unapproved placeholder brand"
            if table in ("brand_alias_registry", "brand_domain_registry") and row.get("brand_id") not in brand_ids:
                reason = "brand not approved"
            if table == "brand_domain_registry" and str(row.get("domain", "")).endswith(".test"):
                reason = "placeholder domain"
            if table == "comparison_registry" and (row.get("query_id") not in accepted["query_registry"] or row.get("prompt_id") not in accepted["llm_prompt_registry"]):
                reason = "missing authoritative query/prompt registry"
            if reason:
                report["excluded"].append({"table": table, "id": key, "reason": reason})
                continue
            if table == "llm_prompt_registry":
                row.setdefault("prompt_group", "")
            if table == "comparison_registry" and "mapping_version" in row:
                # Definition activation uses this build date, not collection date.
                start = date.fromisoformat(row["effective_start_date"])
                end = (date.fromisoformat(row["effective_end_date"])
                       if row.get("effective_end_date") else None)
                if now.date() < start or (end and now.date() > end):
                    row["active"] = False
            row.setdefault("recorded_at", now)
            values = []
            for column in columns:
                value = row.get(column)
                if column == "active" and isinstance(value, str):
                    if value.casefold() not in ("true", "false"):
                        raise ValueError(f"invalid active flag: {table}/{key}")
                    value = value.casefold() == "true"
                if column.endswith("_date") and isinstance(value, str):
                    value = date.fromisoformat(value) if value else None
                values.append(value)
            connection.execute(f"INSERT INTO bronze.{table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
            count += 1
            if table == "brand_registry":
                brand_ids.add(key)
        report["counts"][table] = count
    if not brand_ids:
        report["notes"].append("No approved brands: configured brands are TO_BE_VERIFIED placeholders. Gold brand metrics must remain empty, not copied or invented.")
    return report


def _baidu_parse(parse_input: SERPParseInput, status: str) -> SERPParseResult:
    """Local fixture-backed DataForSEO generic Baidu fields, not Google dispatch."""
    observation_id = identifier(f"baidu|{parse_input.response_id}|{parse_input.raw_file_hash}")
    tasks = parse_input.response_payload["tasks"]
    raw_items = []
    for result in tasks[0].get("result") or []:
        items = result.get("items")
        if items is not None and not isinstance(items, list):
            raise ValueError("malformed Baidu items")
        raw_items.extend(items or [])
    observation = SearchObservation(observation_id, parse_input.query_id, parse_input.provider,
        "baidu", parse_input.search_type, parse_input.location_code, parse_input.language_code,
        parse_input.device, parse_input.collection_window, parse_input.response_id,
        parse_input.source_ingestion_id, parse_input.raw_file_hash, bool(raw_items),
        status if status in ("pending", "provider_error") else "available" if raw_items else "no_results")
    items, quarantine = [], []
    for index, raw in enumerate(raw_items):
        reason = None
        if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
            reason = "malformed_item"
        else:
            if raw["type"] not in ("organic", "featured_snippet"):
                reason = "unknown_item_type"
            ranks = [raw.get("rank_group"), raw.get("rank_absolute")]
            rank_group, rank_absolute = [v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None for v in ranks]
            if any(v is not None and normalized is None for v, normalized in zip(ranks, (rank_group, rank_absolute), strict=True)):
                reason = "invalid_rank"
            url = raw.get("url") if isinstance(raw.get("url"), str) else None
            parsed_url = urlsplit(url or "")
            canonical = urlunsplit((parsed_url.scheme.lower(), parsed_url.netloc.lower(), parsed_url.path, parsed_url.query, "")) if parsed_url.scheme in ("http", "https") and parsed_url.netloc else None
            domain = raw.get("domain") if isinstance(raw.get("domain"), str) else None
            domain = domain or parsed_url.hostname
            items.append(SERPItem(identifier(f"{observation_id}|{index}|{dump(raw)}"), observation_id,
                "baidu", parse_input.response_id, parse_input.source_ingestion_id, parse_input.raw_file_hash,
                index, raw["type"], raw["type"] if raw["type"] in ("organic", "featured_snippet") else "unknown",
                rank_group, rank_absolute, raw.get("page") if isinstance(raw.get("page"), int) else None,
                rank_group, raw.get("domain"), domain.casefold().rstrip(".") if domain else None,
                url, canonical, raw.get("title"), raw.get("description"), dump(raw), "baidu_generic_raw_full", "1",
                "1", "warning" if reason else "normalized", reason))
        if reason:
            quarantine.append(SERPParsingQuarantine(identifier(f"{observation_id}|{index}|{reason}"),
                observation_id, "baidu", parse_input.response_id, parse_input.source_ingestion_id,
                parse_input.raw_file_hash, index, reason, dump(raw), "baidu_generic_raw_full", "1"))
    return SERPParseResult(observation, tuple(items), tuple(quarantine))


def _rekey_serp(parsed: SERPParseResult, status: str) -> SERPParseResult:
    """No collision even before shared parser adds response/hash to its grain."""
    obs = parsed.observation
    key = identifier(f"raw-full|{obs.observation_id}|{obs.response_id}|{obs.raw_file_hash}")
    outcome = status if status in ("pending", "provider_error") else "quarantined" if any(q.item_index is None for q in parsed.quarantine) else obs.outcome_status
    return SERPParseResult(replace(obs, observation_id=key, outcome_status=outcome),
        tuple(replace(item, observation_id=key, serp_item_id=identifier(f"{key}|{item.item_index}|{item.raw_item_json}")) for item in parsed.items),
        tuple(replace(q, observation_id=key, quarantine_id=identifier(f"{key}|{q.item_index}|{q.reason}|{q.raw_item_json}")) for q in parsed.quarantine))


def _features(parsed: SERPParseResult) -> SERPFeatureResult:
    if parsed.observation.search_engine != "baidu":
        return parse_serp_features(parsed)
    obs = parsed.observation
    return SERPFeatureResult(tuple(OrganicResult(identifier(f"{item.serp_item_id}|organic"), obs.provider,
        "baidu", obs.search_type, obs.observation_id, item.serp_item_id, item.raw_item_type, True, True,
        item.normalization_status, item.raw_item_json, item.rank_absolute, item.rank_absolute,
        item.raw_url, item.canonical_url, item.title, item.description)
        for item in parsed.items if item.normalized_item_type == "organic" and item.rank_absolute is not None))


def transform_response(database: Any, raw_root: Path, row: dict, context: dict) -> dict:
    """One verified response; repository operations are local and idempotent."""
    path = raw_root / row["path"]
    metadata = _json_bytes((path.parent / "metadata.json").read_bytes())
    payload_bytes = path.read_bytes()
    if hashlib.sha256(payload_bytes).hexdigest() != row["sha256"]:
        raise ValueError("response changed after audit")
    payload = _json_bytes(payload_bytes)
    request_bytes = (path.parent / "request.json").read_bytes()
    if hashlib.sha256(request_bytes).hexdigest() != metadata["files"]["request.json"]["sha256"]:
        raise ValueError("request changed after audit")
    request = _json_bytes(request_bytes)
    family, block = envelope(payload)
    status, task, data = provider_status(block)
    request_id = metadata["request_id"]
    engine = metadata["platform_or_engine"].casefold()
    if metadata["provider"].casefold() != "dataforseo":
        return {"disposition": "unsupported_provider", "status": "unsupported"}
    if row["category"] == "serp" and engine not in supported_serp_engines() | {"baidu"}:
        return {"disposition": "unsupported_engine", "status": "unsupported"}
    if row["category"] == "llm" and engine not in ("chat_gpt", "gemini"):
        return {"disposition": "unsupported_platform", "status": "unsupported"}
    response_id = f"{request_id}-response"
    window = context.get("collection_window") or f"raw-request:{request_id}"
    collected_at = datetime.fromisoformat(metadata["collected_at"])
    record = RawEvidence(source_category=row["category"], provider=metadata["provider"],
        platform_or_engine=engine, run_id=metadata["run_id"], request_id=request_id,
        collected_at=collected_at, request_payload=request, response_payload=payload,
        query_id=context.get("query_id"), search_target_id=context.get("search_target_id"),
        collection_window=window, model_name=context.get("model_name") or data.get("model"),
        request_hash=context.get("request_hash"), deduplication_key=context.get("deduplication_key"),
        request_status="submitted_pending_result" if status == "pending" else "provider_error" if status == "provider_error" else "completed")
    raw_files = []
    for name in ("request.json", "response.json"):
        file = metadata["files"][name]
        raw_files.append(RawFile(path.parent / name, file["sha256"], file["byte_size"], file["content_type"]))
    result = RawWriteResult(path.parent, *raw_files, RawFile(path.parent / "metadata.json", "", 0, "application/json"))
    with database.transaction() as connection:
        existing = connection.execute("SELECT sha256 FROM bronze.raw_files WHERE request_id=? AND artifact_type='response'", [request_id]).fetchone()
    if existing:
        if existing[0] != row["sha256"]:
            raise ValueError("request_id collision with different response SHA")
        return {"disposition": "already_transformed", "status": "idempotent"}
    # Parse before Bronze commit: parser failures never manufacture completed rows.
    if row["category"] == "serp":
        parse_input = SERPParseInput(context.get("query_id") or f"raw-request:{request_id}",
            metadata["provider"], engine, str(data.get("se_type") or "unknown"),
            str(data.get("location_code") or "unknown"), str(data.get("language_code") or "unknown"),
            str(data.get("device") or "unknown"), window, response_id, metadata["run_id"], row["sha256"], block)
        parsed = _rekey_serp(_baidu_parse(parse_input, status) if engine == "baidu" else parse_serp_response(parse_input), status)
        feature_result = _features(parsed)
        outcome = parsed.observation.outcome_status
    else:
        results = task.get("result") or []
        if len(results) > 1:
            raise ValueError("unsupported multiple LLM results; do not truncate")
        if status in ("pending", "provider_error", "no_results"):
            flattened = {"items": [], "citations": [], "response_text": None}
        else:
            # Never mutate raw; live/direct/get contract normalized on a deep copy.
            flattened = transform_llm_raw_payload({"retrieval": copy.deepcopy(block)})
        outcome = status if status != "available" else str(flattened.get("outcome_status") or ("available" if flattened.get("items") or flattened.get("response_text") else "no_results"))
        observation = SilverLLMObservation(identifier(f"{request_id}|{response_id}|{row['sha256']}|llm"),
            request_id, response_id, metadata["provider"], engine,
            str(flattened.get("model") or context.get("model_name") or data.get("model") or "unknown"),
            flattened.get("query") or data.get("keyword"), task.get("id"), task.get("status_code"),
            task.get("cost"), flattened.get("language_code") or data.get("language_code"),
            str(flattened.get("location_code") or data.get("location_code")) if flattened.get("location_code") or data.get("location_code") else None,
            len(flattened.get("items") or []), flattened.get("response_text"), dump(flattened.get("items") or []),
            dump(flattened.get("citations") or []), row["sha256"], "llm_raw_flatten", "raw-full-1", outcome)
    # One outer repository transaction: adapters below share it, avoiding partial
    # Bronze/Silver commits when an unexpected constraint failure occurs.
    class Joined:
        @contextmanager
        def transaction(self):
            yield database.connection
    with database.transaction() as connection:
        joined = Joined()
        RawEvidenceRepository(joined, RawStore(raw_root)).record(record, result)
        connection.execute("UPDATE bronze.api_responses SET task_id=?, actual_cost=? WHERE request_id=?", [task.get("id"), task.get("cost"), request_id])
        if row["category"] == "serp":
            SilverSERPRepository(joined).record(parsed)
            SilverSERPFeatureRepository(joined).record(feature_result)
        else:
            SilverLLMRepository(joined).record(observation)
    return {"disposition": "transformed", "status": outcome, "family": family,
            "query_id": context.get("query_id"), "target_id": context.get("search_target_id"),
            "collection_window": window, "window_source": "authoritative" if context.get("collection_window") else "request_isolated",
            "provider_status_code": task.get("status_code"), "provider_status_message": task.get("status_message"),
            "item_count": len(parsed.items) if row["category"] == "serp" else observation.items_count,
            "quarantine_count": len(parsed.quarantine) if row["category"] == "serp" else int(outcome == "quarantined")}


def write_reports(export: Path, manifest: list[dict], requests: list[dict], summary: dict) -> None:
    export.mkdir(parents=True, exist_ok=True)
    for name, value in (("manifest", manifest), ("request_statuses", requests), ("summary", summary)):
        (export / f"{name}.json").write_text(dump(value) + "\n", encoding="utf-8")
        if isinstance(value, list) and value:
            columns = sorted({key for row in value for key in row})
            with (export / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows({key: dump(value) if isinstance(value, (dict, list)) else value for key, value in row.items()} for row in value)


def run(project: Path, *, audit_only: bool = False, raw_date: date | None = None) -> dict:
    project = project.resolve()
    started = datetime.now(UTC)
    start = time.monotonic()
    stamp = started.strftime("%Y%m%dT%H%M%S_%fZ")
    raw_root = project / "data/raw"
    prefix = f"raw_date_{raw_date:%Y%m%d}" if raw_date else "raw_full"
    output = project / f"data/warehouse/{prefix}_{stamp}.duckdb"
    export = project / f"data/exports/{prefix}_{stamp}"
    export.mkdir(parents=True, exist_ok=False)
    sources = sorted(
        path for path in (project / "data/warehouse").glob("*.duckdb")
        if not path.name.startswith(("raw_full_", "raw_date_"))
    )  # Derived raw-request windows are never authoritative on a subsequent run.
    manifest = audit_raw(raw_root, raw_date)
    candidates = [row for row in manifest if row["role"] == "response"]
    summary: dict[str, Any] = {"started_at": started, "database": str(output) if not audit_only else None,
        "export": str(export), "audit_only": audit_only, "json_files": len(manifest),
        "raw_folder_date": raw_date.isoformat() if raw_date else None,
        "date_filter_basis": "raw folder YYYY/MM/DD, not result datetime",
        "roles": dict(Counter(row["role"] for row in manifest)),
        "categories": dict(Counter(row["category"] for row in manifest)),
        "json_invalid": sum(not row["json_valid"] for row in manifest),
        "response_files": len(candidates), "integrity_invalid_responses": sum(not row["triple_valid"] for row in candidates),
        "dbt_run": False, "publication": False, "gold_status": "deferred_to_main_dbt_no_copied_metrics"}
    requests = []
    # Write audit checkpoint even if later initialization fails.
    write_reports(export, manifest, requests, summary)
    if audit_only:
        summary["elapsed_seconds"] = round(time.monotonic() - start, 3)
        write_reports(export, manifest, requests, summary)
        return summary
    index, registry_provenance, source_reports = read_provenance(sources)
    summary["provenance_sources"] = source_reports
    if output.exists():
        raise FileExistsError(output)
    DuckDBStore(output).initialize()  # Includes empty migrated presentation snapshot schema.
    seen: dict[str, str] = {}
    used: dict[str, set[str]] = defaultdict(set)
    with duckdb.connect(str(output)) as connection:
        connection.execute("SET TimeZone='UTC'")
        connection.execute("SET threads=1")  # Small atomic inserts: avoid worker fan-out.
        database = _LocalDatabase(connection)
        for number, row in enumerate(candidates, start=1):
            request_report = {"path": row["path"], "category": row["category"],
                              "request_id": row["request_id"], "sha256": row["sha256"],
                              "engine_or_platform": row["engine_or_platform"], "collected_at": row["collected_at"]}
            if not row["triple_valid"]:
                request_report.update(disposition="quarantined_integrity", status="quarantined", error=row["integrity_problems"])
            else:
                try:
                    metadata = _json_bytes((raw_root / row["path"]).with_name("metadata.json").read_bytes())
                    context, provenance_paths, conflicts = reconcile_context(metadata, row["sha256"], index)
                    request_report.update(context_sources=provenance_paths, context_conflicts=conflicts)
                    if conflicts:
                        raise ValueError(f"conflicting authoritative context: {conflicts}")
                    previous = seen.get(row["request_id"])
                    if previous is not None:
                        if previous != row["sha256"]:
                            raise ValueError("duplicate request ID with different SHA")
                        request_report.update(disposition="duplicate_response", status="duplicate")
                    else:
                        request_report.update(transform_response(database, raw_root, row, context))
                        if request_report["disposition"] == "transformed":
                            seen[row["request_id"]] = row["sha256"]
                            for source in provenance_paths:
                                used[source].update(value for key, value in context.items() if key in ("query_id", "search_target_id"))
                except Exception as exc:
                    request_report.update(disposition="quarantined_transform", status="quarantined", error=f"{type(exc).__name__}: {exc}")
            row["disposition"] = request_report["disposition"]
            requests.append(request_report)
            if number % 500 == 0:
                print(f"processed {number}/{len(candidates)}", flush=True)
        summary["registries"] = seed_registries(connection, project / "config/registries", registry_provenance, used, started)
        summary["response_evidence_observations"] = enrich_database(
            connection, raw_root, project / "config/registries/category_rules.csv"
        )
        summary["candidate_review_rows"] = export_candidate_review(connection, export / "candidate_review.csv")
        summary["feature_evidence_version"] = "feature-evidence-2"
        connection.execute("CREATE TABLE meta.raw_full_request_statuses (path VARCHAR, request_id VARCHAR, status VARCHAR, disposition VARCHAR, details_json VARCHAR)")
        connection.executemany("INSERT INTO meta.raw_full_request_statuses VALUES (?, ?, ?, ?, ?)",
            [(r["path"], r["request_id"], r["status"], r["disposition"], dump(r)) for r in requests]) if requests else None
        summary["tables"] = {}
        for schema, table in connection.execute("SELECT table_schema,table_name FROM information_schema.tables WHERE table_schema IN ('bronze','silver','presentation','meta') ORDER BY 1,2").fetchall():
            relation = f'"{schema}"."{table}"'
            count = connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
            summary["tables"][f"{schema}.{table}"] = count
            destination = str(export / f"{schema}.{table}.parquet").replace("'", "''")
            connection.execute(f"COPY {relation} TO '{destination}' (FORMAT PARQUET)")
    summary["statuses"] = dict(Counter(row["status"] for row in requests))
    summary["dispositions"] = dict(Counter(row["disposition"] for row in manifest))
    summary["supported_responses"] = sum(row["disposition"] == "transformed" for row in requests)
    summary["unsupported_responses"] = sum(row["status"] == "unsupported" for row in requests)
    summary["quarantined_responses"] = sum(row["status"] == "quarantined" for row in requests)
    summary["parse_quarantine_events"] = sum(row.get("quarantine_count", 0) for row in requests)
    summary["context_reconciled"] = sum(bool(row.get("context_sources")) for row in requests)
    summary["authoritative_query_context"] = sum(bool(row.get("query_id")) for row in requests)
    summary["authoritative_windows"] = sum(row.get("window_source") == "authoritative" for row in requests)
    summary["per_engine_statuses"] = {engine: dict(Counter(row["status"] for row in requests if str(row["engine_or_platform"]).casefold() == engine)) for engine in sorted({str(row["engine_or_platform"]).casefold() for row in requests})}
    final = audit_raw(raw_root, raw_date)
    summary["raw_unchanged"] = {r["path"]: r["sha256"] for r in final} == {r["path"]: r["sha256"] for r in manifest}
    summary["all_files_accounted"] = sum(summary["dispositions"].values()) == len(manifest) and not any(row["disposition"] in ("unreviewed", "verified_response_candidate") for row in manifest)
    summary["response_reconciliation"] = sum(summary["statuses"].values()) == len(candidates)
    summary["completed_at"] = datetime.now(UTC)
    summary["elapsed_seconds"] = round(time.monotonic() - start, 3)
    write_reports(export, manifest, requests, summary)
    if not summary["raw_unchanged"] or not summary["all_files_accounted"] or not summary["response_reconciliation"]:
        raise RuntimeError("raw mutation or count reconciliation failure; inspect summary")
    return summary


def finalize_dbt_export(export: Path) -> dict:
    """Export successful dbt results, without publishing an ineligible release."""
    summary_path = export / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    results = json.loads((export / "dbt_target/run_results.json").read_text(encoding="utf-8"))
    failures = [row for row in results["results"] if row["status"] not in ("success", "pass")]
    if failures:
        raise ValueError("dbt failed or skipped nodes; do not mark transformation validated")
    with duckdb.connect(summary["database"]) as connection:
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='analytics' ORDER BY table_name"
        ).fetchall()
        for (table,) in tables:
            relation = f'analytics."{table}"'
            summary["tables"][f"analytics.{table}"] = connection.execute(
                f"SELECT count(*) FROM {relation}"
            ).fetchone()[0]
            destination = str(export / f"analytics.{table}.parquet").replace("'", "''")
            connection.execute(f"COPY {relation} TO '{destination}' (FORMAT PARQUET)")
        approved_brands = connection.execute("SELECT count(*) FROM bronze.brand_registry").fetchone()[0]
        comparisons = connection.execute("SELECT count(*) FROM bronze.comparison_registry WHERE active=true").fetchone()[0]
    summary.update(
        dbt_run=True,
        dbt_results=dict(Counter(row["status"] for row in results["results"])),
        gold_status="built_empty_no_approved_brands" if not approved_brands else "built",
        publication=False,
        publication_blockers=(
            (["no_approved_brand_registry"] if not approved_brands else [])
            + (["no_active_approved_comparisons"] if not comparisons else [])
        ),
    )
    summary_path.write_text(dump(summary) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--raw-date", type=date.fromisoformat,
                        help="Only raw folders with this YYYY-MM-DD date")
    parser.add_argument("--finalize-export", type=Path,
                        help="Export views after successful offline dbt build")
    args = parser.parse_args()
    result = (finalize_dbt_export(args.finalize_export) if args.finalize_export
              else run(args.project, audit_only=args.audit_only, raw_date=args.raw_date))
    print(dump(result), flush=True)


if __name__ == "__main__":
    main()