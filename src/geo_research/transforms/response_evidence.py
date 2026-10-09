# ruff: noqa: E501
"""Conservative, offline response enrichment; never approves inferred identities."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

VERSION = "response-evidence-1"
TABLES = (
    "silver_response_summaries", "silver_response_items",
    "silver_item_brand_evidence", "silver_item_category_evidence",
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _id(*parts: object) -> str:
    return str(uuid5(NAMESPACE_URL, _json(parts)))


def _rows(connection: Any, query: str) -> list[dict]:
    result = connection.execute(query)
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def _valid(row: dict, as_of: date) -> bool:
    start, end = row.get("effective_start_date"), row.get("effective_end_date")
    return (not start or str(start)[:10] <= as_of.isoformat()) and (
        not end or as_of.isoformat() <= str(end)[:10]
    )


def _placeholder(value: object) -> bool:
    text = str(value).casefold()
    return any(word in text for word in (
        "to_be_verified", "example", "placeholder", "sanitized", "範例", "示例",
    ))


def load_brand_registry(connection: Any) -> dict:
    """Read actual Bronze only. Activity alone is not ownership approval."""
    tables = {row[0] for row in connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='bronze'"
    ).fetchall()}
    required = {"brand_registry", "brand_alias_registry", "brand_domain_registry"}
    raw = {table: _rows(connection, f"SELECT * FROM bronze.{table}")
           for table in sorted(required & tables)}
    version = hashlib.sha256(_json({key: sorted(rows, key=_json) for key, rows in raw.items()}).encode()).hexdigest()
    brands = {row["brand_id"]: row for row in raw.get("brand_registry", [])
              if row.get("active") is True
              and str(row.get("ownership_type", "")).casefold() in {"owned", "competitor"}
              and not _placeholder(row)}
    return {"brands": brands, "aliases": raw.get("brand_alias_registry", []),
            "domains": raw.get("brand_domain_registry", []), "version": version}


def load_category_rules(path: Path | None) -> list[dict]:
    """No default classifications. Only explicit approved active CSV rules apply."""
    if path is None or not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    approved = []
    for row in rows:
        if row.get("review_status") != "approved" or row.get("active", "").lower() != "true":
            continue
        if not all(row.get(key) for key in (
            "rule_id", "category_id", "category_name", "term", "matched_field",
            "item_kind", "taxonomy_version", "rule_version",
        )) or _placeholder(row):
            raise ValueError("approved category rule has missing/placeholder fields")
        if row["matched_field"] not in {
            "title", "description", "text", "original_text", "markdown", "brand",
            "category", "product_category",
        }:
            raise ValueError("category rules cannot classify from merchant/source metadata")
        approved.append(row)
    if len({row["rule_id"] for row in approved}) != len(approved):
        raise ValueError("duplicate approved category rule ID")
    return approved


def spans(text: str, terms: list[tuple[str, str]]) -> list[tuple[str, int, int, str]]:
    """Casefold, Unicode boundaries for Latin; longest nonoverlapping CJK spans.

    Return original-text offsets, including casefold expansions such as ß -> ss.
    Equal longest aliases belonging to multiple brands remain many-to-many.
    """
    folded, offsets = "", []
    for index, char in enumerate(text):
        part = char.casefold()
        folded += part
        offsets.extend([index] * len(part))
    candidates = []
    for identity, term in terms:
        needle = term.strip().casefold()
        if not needle:
            continue
        cjk = bool(re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", needle))
        for match in re.finditer(re.escape(needle), folded):
            start, end = match.span()
            if not cjk and (
                (start and (folded[start - 1].isalnum() or folded[start - 1] == "_"))
                or (end < len(folded) and (folded[end].isalnum() or folded[end] == "_"))
            ):
                continue
            candidates.append((identity, offsets[start], offsets[end - 1] + 1, term))
    accepted = []
    for candidate in sorted(set(candidates), key=lambda x: (-(x[2] - x[1]), x[1], x[0])):
        if any(candidate[1] < old[2] and old[1] < candidate[2]
               and candidate[1:3] != old[1:3] for old in accepted):
            continue
        accepted.append(candidate)
    return accepted


def hostname(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value if "://" in value else "https://" + value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return None
        host = parsed.hostname
        return host.rstrip(".").encode("idna").decode().casefold() if host else None
    except (ValueError, UnicodeError):
        return None


def _answer_text(value: str) -> str:
    # Link labels are answer text; URL tokens are citation evidence, not mentions.
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", lambda m: m[1], value)


def enrich_response(context: dict, payload: object, registry: dict,
                    rules: list[dict] | None = None) -> dict[str, list[dict]]:
    """One existing observation, retaining all supported SERP result contexts.

    LLM supports exactly one task/result (same bulk contract). Unsupported shapes
    are explicit, never successful empty evidence. Counts are null unless complete.
    """
    rules = rules or []
    obs = context["observation_id"]
    items: list[dict] = []
    brands: list[dict] = []
    categories: list[dict] = []
    issues: list[str] = []
    counts = dict.fromkeys(("organic", "product_card", "answer_block", "image", "citation"), 0)
    as_of = date.fromisoformat(str(context.get("collected_at") or date.today())[:10])
    approved = {key: row for key, row in registry["brands"].items() if _valid(row, as_of)}
    terms = [(key, row["canonical_name"]) for key, row in approved.items()]
    terms += [(row["brand_id"], row["alias_text"]) for row in registry["aliases"]
              if row["brand_id"] in approved and _valid(row, as_of)
              and not _placeholder(row["alias_text"])]
    domains = [(row["brand_id"], hostname(row.get("domain"))) for row in registry["domains"]
               if row["brand_id"] in approved and _valid(row, as_of)
               and not _placeholder(row.get("domain"))
               and not str(row.get("domain", "")).endswith(".test")]

    def visit(raw: object, path: str, parent: str | None, kind: str) -> None:
        item_id = _id(obs, path, VERSION)
        data = raw if isinstance(raw, dict) else {}
        raw_type = data.get("type")
        known = kind != "unsupported"
        record = {"item_id": item_id, "observation_id": obs, "parent_item_id": parent,
                  "json_path": path, "item_kind": kind, "raw_item_type": raw_type,
                  "raw_evidence_json": _json(raw), "coverage_status": "complete" if known else "partial",
                  "enrichment_version": VERSION}
        items.append(record)
        if not known:
            issues.append(path + ":unsupported_item_type")
        if kind in counts:
            counts[kind] += 1
        fields: dict[str, str] = {}
        evidence_type = None
        if kind == "product_card":
            evidence_type = "product_card"
            fields = {key: data[key] for key in ("title", "description", "brand")
                      if isinstance(data.get(key), str)}
        elif kind == "answer_block":
            evidence_type = "answer_text"
            for key in ("original_text", "markdown", "text"):
                if isinstance(data.get(key), str) and data[key]:
                    fields[key] = _answer_text(data[key])
                    for index, link in enumerate(re.finditer(r"\[[^\]]*\]\((https?://[^)]+)\)", data[key])):
                        visit({"url": link[1], "type": "inline_link"},
                              f"{path}.{key}.inline_links[{index}]", item_id, "citation")
                    break  # alternate representations are not extra mentions
            if not fields:
                issues.append(path + ":answer_content_unavailable")
        elif context["source_category"] == "serp" and kind in {"organic", "serp_item"}:
            evidence_type = "serp_title_snippet"
            fields = {key: data[key] for key in ("title", "description")
                      if isinstance(data.get(key), str)}
        if evidence_type:
            for field, text in fields.items():
                for brand_id, start, end, _ in spans(text, terms):
                    brands.append({"evidence_id": _id(item_id, brand_id, field, start, end),
                                   "observation_id": obs, "item_id": item_id,
                                   "brand_id": brand_id, "brand_name": approved[brand_id]["canonical_name"],
                                   "evidence_type": evidence_type, "matched_field": field,
                                   "matched_text": text[start:end], "span_start": start, "span_end": end,
                                   "method": "reviewed_alias_boundary_longest", "method_version": VERSION,
                                   "registry_version": registry["version"]})
        # Product seller/link host is not evidence of product manufacturer.
        if kind in {"organic", "serp_item", "citation"}:
            field = "url" if data.get("url") else "domain"
            host = hostname(data.get(field))
            for brand_id, registered in domains:
                if host and registered and (host == registered or host.endswith("." + registered)):
                    brands.append({"evidence_id": _id(item_id, brand_id, "host", field),
                                   "observation_id": obs, "item_id": item_id, "brand_id": brand_id,
                                   "brand_name": approved[brand_id]["canonical_name"],
                                   "evidence_type": "citation" if kind == "citation" else "owned_domain",
                                   "matched_field": field, "matched_text": host, "span_start": None,
                                   "span_end": None, "method": "registered_hostname_exact_suffix",
                                   "method_version": VERSION, "registry_version": registry["version"]})
        category_fields = fields | {key: data[key] for key in ("category", "product_category")
                                   if kind == "product_card" and isinstance(data.get(key), str)}
        for rule in rules:
            field = rule["matched_field"]
            if rule["item_kind"] not in {kind, "*"} or field not in category_fields:
                continue
            matches = spans(category_fields[field], [(rule["rule_id"], rule["term"])])
            if matches:
                categories.append({"evidence_id": _id(item_id, rule["rule_id"], field),
                                   "observation_id": obs, "item_id": item_id,
                                   "category_id": rule["category_id"], "category_name": rule["category_name"],
                                   "matched_field": field, "matched_text": matches[0][3],
                                   "method": "reviewed_raw_category_map" if field in {"category", "product_category"}
                                   else "reviewed_explicit_term", "taxonomy_version": rule["taxonomy_version"],
                                   "rule_id": rule["rule_id"], "rule_version": rule["rule_version"]})
        children = {"images": "image", "sources": "citation", "references": "citation"}
        if kind == "product_module":
            children["items"] = "product_card"
        elif kind == "related_module":
            children["items"] = "related_search"
        elif raw_type == "images":
            children["items"] = "image"
        # Any unrecognized semantic subtree is preserved, explicitly partial.
        ignored = {"price", "rating", "rectangle", "checks", "highlighted", "table",
                   "id_to_token_map", "product_ids"}
        for key, value in data.items():
            if key in children:
                if value is None:
                    if key == "items" or (kind == "answer_block" and key in {"references", "sources"}):
                        issues.append(path + "." + key + ":unavailable")
                    continue
                if not isinstance(value, list):
                    issues.append(path + "." + key + ":malformed_children")
                    continue
                for index, child in enumerate(value):
                    child_kind = children[key]
                    if not isinstance(child, dict) and child_kind not in {"image", "related_search"}:
                        child_kind = "unsupported"
                    visit(child, f"{path}.{key}[{index}]", item_id, child_kind)
            elif isinstance(value, (list, dict)) and value and key not in ignored:
                # Retained in parent raw JSON, not discarded or counted as products.
                issues.append(path + "." + key + ":unsupported_nested_content")
        if kind == "product_module" and "items" not in data:
            issues.append(path + ":product_items_unavailable")
        if any(issue.startswith(path + ":") or issue.startswith(path + ".") for issue in issues):
            record["coverage_status"] = "partial"

    status = context.get("collection_status", "available")
    coverage = "complete"
    top_count = reported = None
    result_types: set[str] = set()
    query_text = context.get("query_text")
    model = context.get("model_name")
    language = context.get("language_code")
    location = context.get("location_code")
    task_id = context.get("task_id")
    status_code = context.get("status_code")
    # Pending/error responses still retain request text and provider/task metadata.
    if isinstance(payload, dict):
        metadata_block = payload
        for key in ("retrieval", "live_advanced", "get", "post"):
            if isinstance(payload.get(key), dict) and "tasks" in payload[key]:
                metadata_block = payload[key]
                break
        metadata_tasks = metadata_block.get("tasks")
        if isinstance(metadata_tasks, list) and len(metadata_tasks) == 1 and isinstance(metadata_tasks[0], dict):
            metadata_task = metadata_tasks[0]
            metadata_data = metadata_task.get("data")
            if isinstance(metadata_data, dict):
                query_text = metadata_data.get("keyword") or query_text
                language = metadata_data.get("language_code") or language
                location = metadata_data.get("location_code") or location
                model = metadata_data.get("model") or model
            task_id = metadata_task.get("id") or task_id
            status_code = metadata_task.get("status_code") or metadata_block.get("status_code")
    if status not in {"available", "no_results"}:
        coverage = status
    elif not isinstance(payload, dict):
        coverage = "missing"
    else:
        block, prefix = payload, "$"
        for key in ("retrieval", "live_advanced", "get", "post"):
            if isinstance(payload.get(key), dict) and "tasks" in payload[key]:
                block, prefix = payload[key], "$." + key
                break
        tasks = block.get("tasks")
        if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], dict):
            coverage = "unsupported"
            issues.append("expected_one_task")
        else:
            task = tasks[0]
            task_id = task.get("id") or task_id
            status_code = task.get("status_code") or block.get("status_code")
            codes = [block.get("status_code"), task.get("status_code")]
            if any(isinstance(code, int) and code >= 40000 for code in codes):
                coverage = "provider_error"
            elif task.get("status_code") in {20100, 20101, 20102, 20103, 20104}:
                coverage = "pending"
            else:
                results = task.get("result")
                if not isinstance(results, list) or (
                    context["source_category"] == "llm" and len(results) > 1
                ):
                    coverage = "unsupported"
                    issues.append("unsupported_result_contract")
                else:
                    top_count = 0
                    structural_complete = True
                    reported_values = []
                    data = task.get("data") or {}
                    query_text = data.get("keyword") or query_text
                    language = data.get("language_code") or language
                    location = data.get("location_code") or location
                    for ri, result in enumerate(results):
                        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
                            issues.append(f"result[{ri}]:items_unavailable")
                            structural_complete = False
                            continue
                        model = result.get("model") or model
                        raw_items = result["items"]
                        top_count += len(raw_items)
                        reported_values.append(result.get("items_count"))
                        base = f"{prefix}.tasks[0].result[{ri}]"
                        for index, raw in enumerate(raw_items):
                            raw_type = raw.get("type", "unknown") if isinstance(raw, dict) else "unknown"
                            result_types.add(str(raw_type))
                            kind = {"organic": "organic", "shopping": "product_module",
                                    "related_searches": "related_module", "images": "serp_item",
                                    "featured_snippet": "serp_item"}.get(raw_type, "unsupported")
                            if context["source_category"] == "llm":
                                kind = "answer_block" if raw_type in {
                                    "chat_gpt_text", "gemini_text", "chat_gpt_table", "gemini_table",
                                } else "product_module" if raw_type in {
                                    "chat_gpt_products", "gemini_products",
                                } else "unsupported"
                            visit(raw, f"{base}.items[{index}]", None, kind)
                        sources = result.get("sources")
                        if isinstance(sources, list):
                            for index, source in enumerate(sources):
                                visit(source, f"{base}.sources[{index}]", None,
                                      "citation" if isinstance(source, dict) else "unsupported")
                        elif sources is not None:
                            issues.append(base + ":malformed_sources")
                    if reported_values and all(isinstance(v, int) for v in reported_values):
                        reported = sum(reported_values)
                    if not structural_complete:
                        top_count = None
                    if issues:
                        coverage = "partial"
    complete = coverage == "complete"
    ids = sorted({row["brand_id"] for row in brands})
    summary = {"observation_id": obs, "source_category": context["source_category"],
               "request_id": context["request_id"], "response_id": context["response_id"],
               "raw_file_hash": context["raw_file_hash"], "query_id": context.get("query_id"),
               "query_text": query_text, "provider": context.get("provider"),
               "engine_or_platform": context.get("engine_or_platform"), "model_name": model,
               "language_code": str(language).replace("_", "-").lower() if language else None,
               "location_code": str(location) if location is not None else None,
               "collected_at": context.get("collected_at"), "collection_status": status,
               "task_id": task_id, "status_code": status_code,
               "evidence_coverage_status": coverage,
               "brand_coverage_status": coverage if not complete else "complete" if approved else "no_approved_registry",
               "category_coverage_status": coverage if not complete else "reviewed_rules" if rules else "unknown_no_reviewed_rules",
               "provider_reported_item_count": reported, "top_level_item_count": top_count,
               "atomic_item_count": len(items) if complete else None,
               **{key + "_count": value if complete else None for key, value in counts.items()},
               "distinct_brand_count": len(ids) if complete and approved else None,
               "brand_ids": ids, "brand_names": [approved[key]["canonical_name"] for key in ids],
               "answer_brand_ids": sorted({r["brand_id"] for r in brands if r["evidence_type"] == "answer_text"}),
               "cited_brand_ids": sorted({r["brand_id"] for r in brands if r["evidence_type"] == "citation"}),
               "result_types": sorted(result_types),
               "business_categories": sorted({r["category_id"] for r in categories}) or ["unknown"],
               "issues_json": _json(issues), "enrichment_version": VERSION,
               "registry_version": registry["version"]}
    brands = list({row["evidence_id"]: row for row in brands}.values())
    return dict(zip(TABLES, ([summary], items, brands, categories), strict=True))


def persist_evidence(connection: Any, evidence: dict[str, list[dict]]) -> None:
    """Caller owns transaction: all four tables replace one observation atomically."""
    obs = evidence[TABLES[0]][0]["observation_id"]
    for table in reversed(TABLES):
        connection.execute(f"DELETE FROM silver.{table} WHERE observation_id=?", [obs])
    for table, records in evidence.items():
        if records:
            columns = list(records[0])
            connection.executemany(
                f"INSERT INTO silver.{table} ({','.join(columns)}) "
                f"VALUES ({','.join('?' for _ in columns)})",
                [[row[column] for column in columns] for row in records],
            )


def enrich_database(connection: Any, raw_root: Path, rules_path: Path | None = None) -> int:
    """Enrich existing observations in a NEW bulk warehouse after registry seeding."""
    from geo_research.transforms.feature_evidence import (
        enrich_features,
        load_candidates,
        persist_features,
    )

    registry = load_brand_registry(connection)
    rules = load_category_rules(rules_path)
    candidates = load_candidates(rules_path.parent / "brand_candidates.csv" if rules_path else None)
    candidate_rules = []
    candidate_path = rules_path.parent / "category_candidates.csv" if rules_path else None
    if candidate_path and candidate_path.exists():
        with candidate_path.open(encoding="utf-8-sig", newline="") as handle:
            candidate_rules = [row for row in csv.DictReader(handle)
                               if row.get("review_status") == "candidate"
                               and row.get("active", "").lower() == "true"]
    contexts = _rows(connection, """
        SELECT s.observation_id, 'serp' AS source_category, r.request_id,
            s.response_id, s.raw_file_hash, r.query_id, NULL AS query_text,
            s.provider, s.search_engine AS engine_or_platform, NULL AS model_name,
            s.language_code, s.location_code, p.received_at AS collected_at,
            s.outcome_status AS collection_status, f.raw_directory, f.relative_path
        FROM silver.silver_search_observations s
        JOIN bronze.api_responses p USING(response_id)
        JOIN bronze.api_requests r ON r.request_id=p.request_id
        LEFT JOIN bronze.raw_files f ON f.request_id=r.request_id AND f.artifact_type='response'
        UNION ALL
        SELECT s.observation_id, 'llm', s.request_id, s.response_id, s.raw_file_hash,
            r.query_id, s.query_text, s.provider, s.platform, s.model_name,
            s.language_code, s.location_code, p.received_at, s.outcome_status,
            f.raw_directory, f.relative_path
        FROM silver.silver_llm_observations s
        JOIN bronze.api_responses p USING(response_id)
        JOIN bronze.api_requests r ON r.request_id=s.request_id
        LEFT JOIN bronze.raw_files f ON f.request_id=r.request_id AND f.artifact_type='response'
    """)
    for context in contexts:
        payload = None
        if context.get("relative_path"):
            path = raw_root / context["relative_path"]
            if not path.is_file():
                path = Path(context["raw_directory"]) / Path(context["relative_path"]).name
            try:
                content = path.read_bytes()
                if hashlib.sha256(content).hexdigest() == context["raw_file_hash"]:
                    payload = json.loads(content)
            except (OSError, ValueError):
                pass
        connection.execute("BEGIN TRANSACTION")
        try:
            persist_evidence(connection, enrich_response(context, payload, registry, rules))
            persist_features(connection, enrich_features(
                context, payload, registry, rules, candidates, candidate_rules,
            ))
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    return len(contexts)