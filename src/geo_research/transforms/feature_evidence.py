# ruff: noqa: E501, B023
# Result-local recursive helpers execute synchronously and never escape the loop.
"""Additive, result-grained v2 evidence. No inferred approvals or API calls."""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from geo_research.transforms.brand_discovery import discover_explicit_brands
from geo_research.transforms.response_evidence import (
    _id,
    _json,
    _placeholder,
    _valid,
    hostname,
    spans,
)

VERSION = "feature-evidence-2"
TABLES = (
    "evidence_results_v2", "evidence_items_v2", "evidence_features_v2",
    "evidence_citations_v2", "evidence_citation_occurrences_v2", "evidence_matches_v2",
)
FEATURES = ("organic", "paid", "answer_text", "product", "citation")
LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")


def canonical_url(value: object) -> str | None:
    """Conservative entity identity: retain query/path; no tracking guesses."""
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        return None
    host = hostname(value)
    if not host:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
        netloc = f"[{host}]" if ":" in host else host
        if port and (parsed.scheme, port) not in {("http", 80), ("https", 443)}:
            netloc += f":{port}"
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
    except ValueError:
        return None


def visible_text(value: str) -> str:
    value = LINK.sub(lambda match: match[1], value)
    # Bare URL tokens and autolinks are not answer mentions.
    return re.sub(r"<?https?://[^\s<>]+>?", "", value)


def table_text(value: object) -> str | None:
    """Only explicit rectangular scalar cell lists are supported, not dict guesses."""
    if not isinstance(value, list) or not value or not all(isinstance(row, list) for row in value):
        return None
    widths = {len(row) for row in value}
    if len(widths) != 1 or not next(iter(widths)):
        return None
    if any(not isinstance(cell, (str, int, float, bool)) and cell is not None
           for row in value for cell in row):
        return None
    return "\n".join(" | ".join("" if cell is None else str(cell) for cell in row) for row in value)


def load_candidates(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row.get("review_status") == "candidate"
            and all(row.get(key) for key in ("candidate_id", "candidate_name", "alias_text"))]


def enrich_features(context: dict, payload: object, registry: dict,
                    rules: list[dict] | None = None,
                    candidates: list[dict] | None = None,
                    candidate_rules: list[dict] | None = None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {table: [] for table in TABLES}
    obs = context["observation_id"]
    category = context["source_category"]
    as_of = date.fromisoformat(str(context.get("collected_at") or date.today())[:10])
    approved = {key: row for key, row in registry["brands"].items() if _valid(row, as_of)}
    terms = [(key, row["canonical_name"]) for key, row in approved.items()]
    terms += [(row["brand_id"], row["alias_text"]) for row in registry["aliases"]
              if row["brand_id"] in approved and _valid(row, as_of)
              and not _placeholder(row["alias_text"])]
    candidate_terms = [(row["candidate_id"], row["alias_text"]) for row in candidates or []]
    candidate_names = {row["candidate_id"]: row["candidate_name"] for row in candidates or []}
    domains = [(row["brand_id"], hostname(row.get("domain"))) for row in registry["domains"]
               if row["brand_id"] in approved and _valid(row, as_of)
               and not _placeholder(row.get("domain"))
               and not str(row.get("domain", "")).endswith(".test")]
    block, prefix = payload, "$"
    if isinstance(payload, dict):
        for key in ("retrieval", "live_advanced", "get", "post"):
            if isinstance(payload.get(key), dict) and "tasks" in payload[key]:
                block, prefix = payload[key], "$." + key
                break
    tasks = block.get("tasks") if isinstance(block, dict) else None
    status = context.get("collection_status", "available")
    task = tasks[0] if isinstance(tasks, list) and len(tasks) == 1 and isinstance(tasks[0], dict) else {}
    if not task:
        status = status if status not in {"available", "no_results"} else "missing" if payload is None else "unsupported"
    codes = [task.get("status_code"), block.get("status_code") if isinstance(block, dict) else None]
    if any(isinstance(code, int) and code >= 40000 for code in codes):
        status = "provider_error"
    elif task.get("status_code") in {20100, 20101, 20102, 20103, 20104}:
        status = "pending"
    data = task.get("data") if isinstance(task.get("data"), dict) else {}
    results = task.get("result")
    if status in {"available", "no_results"} and (
        not isinstance(results, list) or (category == "llm" and len(results) > 1)
    ):
        status = "unsupported"
    real_results = results if status in {"available", "no_results"} and results else [None]
    for ri, result in enumerate(real_results):
        result = result if isinstance(result, dict) else {}
        base = f"{prefix}.tasks[0].result[{ri}]" if result else prefix
        rid = _id(obs, base, VERSION)
        issues: dict[str, list[str]] = {feature: [] for feature in FEATURES}
        global_issues: list[str] = []
        applicable = set(FEATURES) if category == "serp" else {"answer_text", "product", "citation"}
        if category == "serp":
            applicable -= {"answer_text", "citation"}  # AI modules below explicitly enable these.
        raw_items = result.get("items")
        structure = isinstance(raw_items, list)
        fallback = category == "llm" and isinstance(result.get("markdown"), str) and bool(result["markdown"])
        if not structure:
            for feature in applicable:
                issues[feature].append("items_unavailable")
        parsed = 0
        text_seen = False
        citation_containers = 0

        def match(item: dict, fields: dict[str, str], channel: str) -> None:
            for field, text in fields.items():
                for term_set, identity_type in ((terms, "brand"), (candidate_terms, "brand_candidate")):
                    for identity, start, end, _ in spans(text, term_set):
                        out[TABLES[5]].append({
                            "evidence_id": _id(item["item_id"], identity_type, identity, field, start, end),
                            "observation_id": obs, "result_id": rid, "item_id": item["item_id"],
                            "citation_id": None, "identity_id": identity,
                            "identity_name": approved[identity]["canonical_name"] if identity_type == "brand" else candidate_names[identity],
                            "identity_type": identity_type,
                            "review_status": "approved" if identity_type == "brand" else "candidate",
                            "evidence_type": channel, "matched_field": field,
                            "matched_text": text[start:end], "span_start": start, "span_end": end,
                            "method": "explicit_alias_boundary_longest", "registry_version": registry["version"],
                            "enrichment_version": VERSION,
                        })
            for rule in (rules or []) + (candidate_rules or []):
                field = rule.get("matched_field")
                compatible_kind = {"product": "product_card", "answer_text": "answer_block"}.get(item["item_kind"])
                if item["item_kind"] == "answer_text" and field in {"original_text", "markdown"}:
                    field = "text"
                if rule.get("item_kind") not in {item["item_kind"], compatible_kind, "*"} or field not in fields:
                    continue
                found = spans(fields[field], [(rule["rule_id"], rule["term"])])
                if found:
                    _, start, end, _ = found[0]
                    out[TABLES[5]].append({
                        "evidence_id": _id(item["item_id"], rule["rule_id"], field),
                        "observation_id": obs, "result_id": rid, "item_id": item["item_id"],
                        "citation_id": None, "identity_id": rule["category_id"], "identity_name": rule["category_name"],
                        "identity_type": "category", "review_status": rule["review_status"],
                        "evidence_type": channel, "matched_field": field, "matched_text": fields[field][start:end],
                        "span_start": start, "span_end": end, "method": "explicit_multilabel_rule:" + rule["rule_id"],
                        "registry_version": _json({k: rule[k] for k in ("taxonomy_version", "rule_version")}),
                        "enrichment_version": VERSION,
                    })

        def owned(item: dict, channel: str, cid: str | None = None) -> None:
            host = hostname(item.get("url"))
            if not host and not item.get("url"):
                host = hostname(item.get("domain"))
            for identity, registered in domains:
                if host and registered and (host == registered or host.endswith("." + registered)):
                    out[TABLES[5]].append({
                        "evidence_id": _id(cid or item["item_id"], identity, channel),
                        "observation_id": obs, "result_id": rid, "item_id": item["item_id"],
                        "citation_id": cid, "identity_id": identity, "identity_name": approved[identity]["canonical_name"],
                        "identity_type": "brand", "review_status": "approved", "evidence_type": channel,
                        "matched_field": "hostname", "matched_text": host, "span_start": None, "span_end": None,
                        "method": "registered_hostname_exact_suffix", "registry_version": registry["version"],
                        "enrichment_version": VERSION,
                    })

        def visit(raw: object, path: str, parent: str | None, kind: str, top: bool = False) -> dict:
            nonlocal text_seen
            malformed_kind = kind if not isinstance(raw, dict) and kind in {"organic", "paid", "product", "answer_text", "ad_link"} else None
            if malformed_kind:
                feature = "paid" if malformed_kind == "ad_link" else malformed_kind
                issues[feature].append(path + ":malformed_item")
                kind = "unsupported"
            raw_data = raw if isinstance(raw, dict) else {}
            item = {"item_id": _id(obs, path, VERSION), "observation_id": obs, "result_id": rid,
                    "parent_item_id": parent, "json_path": path, "is_top_level": top,
                    "item_kind": kind, "raw_item_type": raw_data.get("type"),
                    **{field: raw_data.get(field) if isinstance(raw_data.get(field), str) else None
                       for field in ("title", "description", "url", "domain")},
                    **{field: raw_data.get(field) if type(raw_data.get(field)) is int else None
                       for field in ("rank_group", "rank_absolute")},
                    "organic_rank": raw_data.get("rank_group") if kind == "organic" and type(raw_data.get("rank_group")) is int else None,
                    "page_position": raw_data.get("rank_absolute") if type(raw_data.get("rank_absolute")) is int else None,
                    "normalized_text": None, "text_method": None,
                    "coverage_status": "partial" if kind == "unsupported" else "complete",
                    "raw_evidence_json": _json(raw), "enrichment_version": VERSION}
            if not item["domain"] and item["url"]:
                item["domain"] = hostname(item["url"])
            out[TABLES[1]].append(item)
            fields = {field: raw_data[field] for field in ("title", "description") if isinstance(raw_data.get(field), str)}
            if kind in {"organic", "paid", "ad_link"}:
                match(item, fields, "paid_text" if kind != "organic" else "organic_title_snippet")
                owned(item, "owned_organic" if kind == "organic" else "paid_domain")
                if kind == "organic" and (not item["url"] or item["organic_rank"] is None):
                    issues["organic"].append(path + ":url_or_organic_rank_unavailable")
                elif kind in {"paid", "ad_link"} and not item["url"]:
                    issues["paid"].append(path + ":paid_url_unavailable")
            elif kind == "product":
                fields.update({field: raw_data[field] for field in ("brand", "category", "product_category")
                               if isinstance(raw_data.get(field), str)})
                match(item, fields, "product_text")
                # Result-driven names are proposals, even when absent from dictionaries.
                for proposal in discover_explicit_brands([item]):
                    out[TABLES[5]].append({
                        "evidence_id": _id(item["item_id"], proposal["candidate_id"], "explicit_brand"),
                        "observation_id": obs, "result_id": rid, "item_id": item["item_id"],
                        "citation_id": None, "identity_id": proposal["candidate_id"],
                        "identity_name": proposal["candidate_name"],
                        "identity_type": "brand_candidate", "review_status": "candidate",
                        "evidence_type": "product_text", "matched_field": "brand",
                        "matched_text": proposal["matched_text"], "span_start": None,
                        "span_end": None, "method": proposal["method"],
                        "registry_version": registry["version"], "enrichment_version": VERSION,
                    })
            elif kind == "answer_text":
                selected = next((field for field in ("original_text", "markdown", "text")
                                 if isinstance(raw_data.get(field), str) and raw_data[field]), None)
                text = raw_data[selected] if selected else table_text(raw_data.get("table"))
                if text is not None:
                    text_seen = True
                    item["normalized_text"] = visible_text(text)
                    item["text_method"] = selected or "scalar_table_cells"
                    match(item, {"text": item["normalized_text"]}, "answer_text")
                    for index, link in enumerate(LINK.finditer(text)):
                        visit({"url": link[2], "type": "inline_link"}, f"{path}.{selected or 'table'}.inline_links[{index}]", item["item_id"], "citation")
                else:
                    issues["answer_text"].append(path + ":text_unavailable_or_unsupported_table")
                    item["coverage_status"] = "partial"
            elif kind == "citation":
                canonical = canonical_url(raw_data.get("url"))
                cid = _id(rid, canonical, VERSION) if canonical else None
                if canonical:
                    out[TABLES[3]].append({"citation_id": cid, "observation_id": obs,
                                          "result_id": rid, "canonical_url": canonical,
                                          "domain": hostname(canonical), "enrichment_version": VERSION})
                    owned(item, "owned_citation", cid)
                else:
                    issues["citation"].append(path + ":invalid_or_missing_url")
                    item["coverage_status"] = "partial"
                out[TABLES[4]].append({"occurrence_id": item["item_id"], "observation_id": obs,
                                      "result_id": rid, "citation_id": cid, "item_id": item["item_id"],
                                      "parent_item_id": parent, "json_path": path,
                                      "raw_url": raw_data.get("url") if isinstance(raw_data.get("url"), str) else None,
                                      "enrichment_version": VERSION})
            elif kind == "unsupported":
                global_issues.append(path + ":unsupported_item")
                if category == "llm":
                    for feature in ("answer_text", "product", "citation"):
                        issues[feature].append(path + ":unknown_llm_item")
            children = {"images": "image", "sources": "citation", "references": "citation"}
            if kind == "product_module":
                children["items"] = "product"
                if "items" not in raw_data:
                    issues["product"].append(path + ":product_items_missing")
            if kind == "paid":
                children["links"] = "ad_link"
            if kind == "related_module":
                children["items"] = "related_search"
            if raw_data.get("type") == "images":
                children["items"] = "image"
            if kind == "answer_module":
                applicable.update({"answer_text", "citation"})
                children["items"] = "answer_text"
                if "items" not in raw_data:
                    issues["answer_text"].append(path + ":answer_children_missing")
                if not any(key in raw_data for key in ("sources", "references")):
                    issues["citation"].append(path + ":answer_sources_missing")
            if kind == "answer_text" and category == "llm" and not any(key in raw_data for key in ("sources", "references")):
                issues["citation"].append(path + ":sources_missing")
            ignored = {"price", "rating", "rectangle", "checks", "highlighted", "table", "id_to_token_map", "product_ids"}
            for key, value in raw_data.items():
                if key in children:
                    child_kind = children[key]
                    if child_kind == "citation":
                        source_container(value, f"{path}.{key}", item["item_id"])
                    elif value is None:
                        if key == "items":
                            issues["product" if kind == "product_module" else "answer_text"].append(path + ":children_unavailable")
                    elif isinstance(value, list):
                        for index, child in enumerate(value):
                            visit(child, f"{path}.{key}[{index}]", item["item_id"], child_kind)
                    else:
                        feature = "paid" if kind == "paid" else "product" if kind == "product_module" else "answer_text"
                        issues[feature].append(path + ":malformed_children")
                elif isinstance(value, (dict, list)) and value and key not in ignored:
                    # Null ad_aclk is provider metadata, not an unparsed content channel.
                    if kind == "paid" and key == "extra" and isinstance(value, dict) and set(value) <= {"ad_aclk"}:
                        continue
                    global_issues.append(path + "." + key + ":unsupported_nested")
                    item["coverage_status"] = "partial"
                    feature = {"answer_text": "answer_text", "product": "product", "product_module": "product", "paid": "paid"}.get(kind)
                    if feature:
                        issues[feature].append(path + "." + key + ":unsupported_nested")
                    visit(value, path + "." + key, item["item_id"], "retained_nested")
            return item

        def source_container(value: object, path: str, parent: str | None) -> None:
            nonlocal citation_containers
            citation_containers += 1
            if not isinstance(value, list):
                issues["citation"].append(path + ":sources_unavailable")
                return
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]", parent, "citation")

        kinds = {"organic": "organic", "paid": "paid", "shopping": "product_module",
                 "related_searches": "related_module", "images": "serp_module",
                 "featured_snippet": "serp_module", "ai_overview": "answer_module"}
        if category == "llm":
            kinds = {key: kind for platform in ("chat_gpt", "gemini")
                     for key, kind in ((platform + "_text", "answer_text"),
                                       (platform + "_table", "answer_text"),
                                       (platform + "_products", "product_module"))}
        for index, raw in enumerate(raw_items if structure else []):
            kind = kinds.get(raw.get("type") if isinstance(raw, dict) else None, "unsupported")
            item = visit(raw, f"{base}.items[{index}]", None, kind, True)
            # Unique raw top-level items, not quarantine/warning event counts.
            parsed += item["coverage_status"] == "complete"
        if fallback and not text_seen:
            visit({"type": "result_markdown", "markdown": result["markdown"]}, base + ".markdown", None, "answer_text")
            if not structure or not raw_items:
                issues["answer_text"] = [issue for issue in issues["answer_text"] if issue != "items_unavailable"]
        if "sources" in result:
            source_container(result["sources"], base + ".sources", None)
        elif category == "llm":
            issues["citation"].append(base + ":result_sources_missing")
        if category == "llm" and not citation_containers:
            issues["citation"].append("no_explicit_source_container")
        local = [item for item in out[TABLES[1]] if item["result_id"] == rid]
        for feature in FEATURES:
            observed = len({item["item_id"] for item in local if item["item_kind"] == feature
                            and (feature != "answer_text" or item["normalized_text"] is not None)})
            if feature == "citation":
                observed = len({row["citation_id"] for row in out[TABLES[3]] if row["result_id"] == rid})
            coverage = status if status not in {"available", "no_results"} else "not_applicable" if feature not in applicable else "partial" if issues[feature] else "complete"
            available = coverage in {"complete", "partial"}
            out[TABLES[2]].append({"feature_id": _id(rid, feature), "observation_id": obs,
                                   "result_id": rid, "feature": feature, "coverage_status": coverage,
                                   "observed_count": observed if available else None,
                                   "exhaustive_count": observed if coverage == "complete" else None,
                                   "issues_json": _json(issues[feature]), "enrichment_version": VERSION})
        language = result.get("language_code") or data.get("language_code") or context.get("language_code")
        location = result.get("location_code", data.get("location_code", context.get("location_code")))
        out[TABLES[0]].append({
            "result_id": rid, "observation_id": obs,
            **{key: context.get(key) for key in ("request_id", "response_id", "raw_file_hash", "provider", "engine_or_platform", "query_id", "collected_at")},
            "source_category": category, "query_text": result.get("keyword") or data.get("keyword") or context.get("query_text"),
            "language_code": str(language).replace("_", "-").lower() if language else None,
            "location_code": str(location) if location is not None else None,
            "device": data.get("device"), "os": data.get("os"),
            "request_depth": data.get("depth") if type(data.get("depth")) is int else None,
            "provider_result_datetime": result.get("datetime"), "task_id": task.get("id"),
            "task_index": 0 if task else None, "result_index": ri if result else None,
            "json_path": base, "check_url": result.get("check_url"), "model_name": result.get("model") or context.get("model_name"),
            "collection_status": status, "top_level_item_count": len(raw_items) if structure else None,
            "provider_reported_item_count": result.get("items_count") if type(result.get("items_count")) is int else None,
            "parsed_top_level_item_count": parsed if structure else None,
            "parse_success_rate": parsed / len(raw_items) if structure and raw_items else None,
            "issues_json": _json(global_issues), "enrichment_version": VERSION,
        })
    for table, key in ((TABLES[3], "citation_id"), (TABLES[5], "evidence_id")):
        out[table] = list({row[key]: row for row in out[table]}.values())
    return out


def persist_features(connection: Any, evidence: dict[str, list[dict]]) -> None:
    obs = evidence[TABLES[0]][0]["observation_id"]
    for table in reversed(TABLES):
        connection.execute(f"DELETE FROM silver.{table} WHERE observation_id=?", [obs])
    for table, rows in evidence.items():
        if rows:
            columns = list(rows[0])
            connection.executemany(
                f"INSERT INTO silver.{table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [[row[column] for column in columns] for row in rows],
            )


def export_candidate_review(connection: Any, destination: Path) -> int:
    """Repeatable review queue, never a registry promotion or ownership inference."""
    result = connection.execute("""
        SELECT m.*, i.json_path, i.title, i.url, i.domain, r.query_text,
               r.language_code, r.location_code, r.engine_or_platform,
               '' AS reviewer, '' AS decision, '' AS ownership_evidence,
               '' AS approved_registry_id
        FROM silver.evidence_matches_v2 m
        JOIN silver.evidence_items_v2 i USING(item_id)
        JOIN silver.evidence_results_v2 r ON r.result_id=m.result_id
        WHERE m.review_status='candidate' ORDER BY m.evidence_id
    """)
    rows = result.fetchall()
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([column[0] for column in result.description])
        writer.writerows(rows)
    return len(rows)