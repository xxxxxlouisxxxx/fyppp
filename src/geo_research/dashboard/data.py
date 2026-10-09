"""Fixed snapshot queries and evidence-grained exploratory summaries.

Never instantiate DuckDBStore/ReleaseRepository here: both can migrate a warehouse.
Only release metadata, information_schema and the three snapshot tables are read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

from geo_research.storage.research_snapshots import KINDS

TABLES = {
    "serp": "release_serp_brand_visibility",
    "llm": "release_llm_brand_visibility",
    "comparison": "release_comparison_brand_metrics",
}
COMMON = (
    "release_id", "metric_id", "brand_id", "brand_canonical_name",
    "metric_name", "metric_version", "availability_status",
)
CHANNEL = (
    "observation_id", "provider", "numerator", "denominator", "metric_value",
    "collection_status", "response_id", "raw_file_hash",
)
CONTEXT = ("language_code", "location_code", "collection_window")
REQUIRED = {
    "serp": COMMON + CHANNEL + (
        "query_id", "search_engine", "search_type", "collection_window",
        "best_normalized_rank", "has_results",
    ),
    "llm": COMMON + CHANNEL + (
        "prompt_id", "platform", "model_name", "mention_count", "citation_count",
        "request_id",
    ),
    "comparison": COMMON + (
        "comparison_id", "query_id", "prompt_id", "serp_observation_id",
        "llm_observation_id", "serp_availability_status", "llm_availability_status",
        "serp_collection_status", "llm_collection_status", "serp_numerator",
        "serp_denominator", "serp_metric_value", "llm_numerator",
        "llm_denominator", "llm_metric_value", "metric_value",
    ),
}
OPTIONAL = {
    "serp": (
        "language_code", "location_code", "raw_language_code", "raw_location_code",
        "device", "collected_at",
    ),
    "llm": CONTEXT + ("raw_language_code", "raw_location_code", "collected_at"),
    "comparison": CONTEXT + (
        "serp_provider", "search_engine", "search_type", "device", "llm_provider",
        "platform", "model_name", "serp_collected_at", "llm_collected_at",
        "comparison_eligibility",
    ),
}


@dataclass
class Snapshot:
    """One materialized transaction; subsequent UI queries cannot change release."""

    releases: pd.DataFrame = field(default_factory=pd.DataFrame)
    release: dict = field(default_factory=dict)
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    message: str | None = None
    evidence: pd.DataFrame = field(default_factory=pd.DataFrame)
    research: dict[str, pd.DataFrame] = field(default_factory=dict)


@dataclass(frozen=True)
class Filters:
    """None means all; an empty tuple means none; tuple member None means unknown."""

    brands: tuple[str | None, ...] | None = None
    languages: tuple[str | None, ...] | None = None
    locations: tuple[str | None, ...] | None = None
    windows: tuple[str | None, ...] | None = None
    engines: tuple[str | None, ...] | None = None
    platforms: tuple[str | None, ...] | None = None


def load_snapshot(database: str | Path, release_id: str | None = None) -> Snapshot:
    """Load current completed release, or explicitly selected completed release.

    SQL identifiers come solely from module constants. User values are parameters.
    Missing context columns on pre-locale releases become NULL, never defaults.
    No creation, migrations, writes, API calls, or fallback to unpublished data.
    """
    result = Snapshot()
    path = Path(database).expanduser()
    if not path.is_file():
        result.message = (
            "Database not found. Choose an existing completed-release warehouse."
        )
        return result
    try:
        with duckdb.connect(str(path), read_only=True) as connection:
            connection.execute("BEGIN TRANSACTION")
            columns = connection.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = ?", ["presentation"],
            ).fetchall()
            schema: dict[str, set[str]] = {}
            for table, column in columns:
                schema.setdefault(table, set()).add(column)
            metadata = {
                "releases": {
                    "release_id", "status", "created_at", "completed_at",
                    "metric_version", "notes",
                },
                "release_current": {"slot", "release_id"},
            }
            if any(not fields <= schema.get(table, set())
                   for table, fields in metadata.items()):
                result.message = (
                    "Completed-release metadata schema is missing or incompatible."
                )
                return result
            result.releases = connection.execute(
                "SELECT release_id, created_at, completed_at, metric_version, notes "
                "FROM presentation.releases WHERE status = ? "
                "ORDER BY completed_at DESC NULLS LAST, release_id", ["completed"],
            ).fetchdf()
            if result.releases.empty:
                result.message = (
                    "No completed releases. Unpublished data is not displayed."
                )
                return result
            if release_id is None:
                pointer = connection.execute(
                    "SELECT r.release_id FROM presentation.release_current c "
                    "JOIN presentation.releases r ON r.release_id = c.release_id "
                    "WHERE c.slot = ? AND r.status = ?", ["current", "completed"],
                ).fetchall()
                if len(pointer) != 1:
                    result.message = (
                        "No valid completed current release. "
                        "Select a completed release explicitly."
                    )
                    return result
                release_id = pointer[0][0]
            chosen = result.releases[result.releases.release_id == release_id]
            if len(chosen) != 1:
                result.message = "Selected release is not completed or does not exist."
                return result
            result.release = chosen.iloc[0].to_dict()
            for channel, table in TABLES.items():
                fields = schema.get(table, set())
                if not set(REQUIRED[channel]) <= fields:
                    result.message = (
                        f"Release snapshot schema missing or incompatible: {table}."
                    )
                    result.frames.clear()
                    return result
                # Only trusted identifiers; optional legacy context has typed NULLs.
                projection = list(REQUIRED[channel]) + [
                    name if name in fields else f"CAST(NULL AS VARCHAR) AS {name}"
                    for name in OPTIONAL[channel]
                ]
                result.frames[channel] = connection.execute(
                    f"SELECT {', '.join(projection)} FROM presentation.{table} "
                    "WHERE release_id = ?", [release_id],
                ).fetchdf()
            if "release_evidence" in schema:
                evidence_fields = (
                    "release_id", "evidence_id", "metric_id", "observation_id",
                    "source_category", "raw_file_hash", "json_pointer", "evidence_kind",
                    "original_text", "url", "reviewer", "approved_at",
                    "approval_reason",
                    "parser_version", "registry_version", "quality_status",
                )
                if not set(evidence_fields) <= schema["release_evidence"]:
                    raise ValueError("incompatible approved evidence snapshot")
                result.evidence = connection.execute(
                    f"SELECT {', '.join(evidence_fields)} "
                    "FROM presentation.release_evidence WHERE release_id=?",
                    [release_id],
                ).fetchdf()
            if "release_research_rows" in schema:
                required = {"release_id", "kind", "row_id", "payload_json"}
                if not required <= schema["release_research_rows"]:
                    raise ValueError("incompatible research snapshot")
                rows: dict[str, list[dict]] = {kind: [] for kind in KINDS}
                for kind, payload in connection.execute(
                    "SELECT kind, payload_json FROM presentation.release_research_rows "
                    "WHERE release_id=? ORDER BY kind, row_id", [release_id],
                ).fetchall():
                    decoded = json.loads(payload)
                    if kind not in rows or not isinstance(decoded, dict):
                        raise ValueError("invalid research row")
                    rows[kind].append(decoded)
                result.research = {
                    kind: pd.DataFrame(records) for kind, records in rows.items()
                }
            connection.execute("COMMIT")
    except (duckdb.Error, OSError, ValueError):
        result.frames.clear()
        result.evidence = pd.DataFrame()
        result.research.clear()
        result.message = (
            "Cannot read this release warehouse. Check schema, permissions and "
            "whether a writer has the file open. No data was changed."
        )
    return result


def research_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """Independent complete result units; partial evidence shown separately."""
    if metrics.empty:
        return pd.DataFrame()
    columns = ["brand_id", "brand", "feature", "source_category", "provider",
               "engine_or_platform", "language_code", "location_code",
               "collection_window", "metric_version", "registry_version"]
    rows = metrics.drop_duplicates(["result_id", "brand_id", "feature"])
    output = []
    for keys, group in rows.groupby(columns, dropna=False):
        denominator = int(group.presence_denominator.fillna(0).sum())
        numerator = int(group.presence_numerator.fillna(0).sum())
        output.append({
            **dict(zip(columns, keys, strict=True)),
            "presence_numerator": numerator, "presence_denominator": denominator,
            "presence_rate": numerator / denominator if denominator else None,
            "results": len(group),
            "partial_results": int(group.coverage_status.eq("partial").sum()),
            "unavailable_results": int((~group.coverage_status.isin(
                ["complete", "partial"],
            )).sum()),
            "quality_status": "experimental",
        })
    return pd.DataFrame(output)


def filtered(snapshot: Snapshot, filters: Filters) -> dict[str, pd.DataFrame]:
    """Channel-local source filters; source pair filters both apply to comparisons."""
    output = {}
    for channel, original in snapshot.frames.items():
        frame = original.copy()
        selections = [
            ("brand_id", filters.brands), ("language_code", filters.languages),
            ("location_code", filters.locations),
            ("collection_window", filters.windows),
        ]
        if channel != "llm":
            selections.append(("search_engine", filters.engines))
        if channel != "serp":
            selections.append(("platform", filters.platforms))
        for column, values in selections:
            if values is not None:
                mask = frame[column].isin([v for v in values if v is not None])
                if None in values:
                    mask |= frame[column].isna()
                frame = frame[mask]
        output[channel] = frame
    return output


def channel_rows(frame: pd.DataFrame, channel: str) -> pd.DataFrame:
    """Supported metric contract, distinct observation-brand (not paired rows)."""
    name = "serp_organic_sov" if channel == "serp" else "llm_brand_mention"
    rows = frame[
        frame.metric_name.eq(name) & frame.metric_version.eq("1.0.0")
    ].copy()
    return rows.drop_duplicates(["observation_id", "brand_id"])


def presence_summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Available-only binary rates with explicit distinct observation denominators."""
    summaries = []
    for channel in ("serp", "llm"):
        rows = channel_rows(frames[channel], channel)
        for brand_id, group in rows.groupby("brand_id", dropna=False):
            value = group.numerator if channel == "serp" else group.metric_value
            valid = group.availability_status.eq("available") & value.notna()
            available = group[valid]
            present = int((value[valid] > 0).sum())
            count = len(available)
            names = group.brand_canonical_name.dropna()
            summaries.append({
                "brand_id": brand_id,
                "brand": str(names.iloc[0]) if len(names) else str(brand_id),
                "channel": channel.upper(), "present": present,
                "available": count, "observations": len(group),
                "unavailable": len(group) - count,
                "presence_rate": present / count if count else None,
            })
    return pd.DataFrame(summaries, columns=[
        "brand_id", "brand", "channel", "present", "available", "observations",
        "unavailable", "presence_rate",
    ])


def source_statuses(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Status counts are distinct observations, not observation × tracked brands."""
    output = []
    for channel in ("serp", "llm"):
        source = "search_engine" if channel == "serp" else "platform"
        rows = channel_rows(frames[channel], channel).drop_duplicates("observation_id")
        counts = rows.groupby(
            ["provider", source, "availability_status", "collection_status"],
            dropna=False,
        ).size().reset_index(name="observations")
        counts = counts.rename(columns={source: "source"})
        counts.insert(0, "channel", channel.upper())
        output.append(counts)
    return pd.concat(output, ignore_index=True)


def locale_summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Stratify by full instrument mix, never claim a controlled regional effect."""
    output = []
    for channel in ("serp", "llm"):
        rows = channel_rows(frames[channel], channel)
        source = "search_engine" if channel == "serp" else "platform"
        instrument = ["provider", source]
        instrument += ["search_type", "device"] if channel == "serp" else ["model_name"]
        groups = ["language_code", "location_code", "collection_window", *instrument]
        for keys, group in rows.groupby(groups, dropna=False):
            local = presence_summary({
                "serp": group if channel == "serp" else frames["serp"].iloc[:0],
                "llm": group if channel == "llm" else frames["llm"].iloc[:0],
            })
            for record in local.to_dict("records"):
                context = dict(zip(groups, keys, strict=True))
                record.update(context)
                record["locale"] = (
                    f"language={display(context['language_code'])} · "
                    f"location={display(context['location_code'])}"
                )
                record["instrument"] = " · ".join(
                    f"{key}={display(context[key])}" for key in instrument
                )
                output.append(record)
    return pd.DataFrame(output)


def eligible_comparisons(frame: pd.DataFrame) -> pd.DataFrame:
    """Never reinterpret v1 link-share subtraction as a v2 presence indicator."""
    valid = (
        frame.metric_name.eq("comparison_brand_presence")
        & frame.metric_version.eq("2.0.0")
        & frame.comparison_eligibility.eq("matched_context")
        & frame.availability_status.eq("available")
        & frame.serp_availability_status.eq("available")
        & frame.llm_availability_status.eq("available")
        & frame.serp_numerator.notna() & frame.llm_metric_value.notna()
        & frame.metric_value.notna()
    )
    for key in (*CONTEXT, "serp_observation_id", "llm_observation_id"):
        valid &= frame[key].notna()
    rows = frame[valid].copy()
    rows["serp_present"] = rows.serp_numerator > 0
    rows["llm_present"] = rows.llm_metric_value > 0
    return rows.drop_duplicates([
        "comparison_id", "brand_id", "serp_observation_id", "llm_observation_id",
        *CONTEXT, "serp_provider", "search_engine", "search_type", "device",
        "llm_provider", "platform", "model_name",
    ])


PATTERNS = (
    ("SERP present · LLM absent", True, False,
     "Inspect the approved prompt, matching rules and answer extraction before "
     "investigating generative-channel visibility."),
    ("LLM present · SERP absent", False, True,
     "Inspect owned-domain matching and observed organic results; this is not "
     "proof of ranking difficulty or incremental demand."),
    ("Neither channel present", False, False,
     "Check brand relevance and instrument coverage first; absence is not "
     "proof of an unmet market need."),
)


def opportunities(frame: pd.DataFrame) -> list[dict]:
    rows = eligible_comparisons(frame)
    output = []
    for title, serp, llm, investigation in PATTERNS:
        matches = rows[rows.serp_present.eq(serp) & rows.llm_present.eq(llm)]
        output.append({
            "title": title, "pairs": len(matches),
            "serp_observations": matches.serp_observation_id.nunique(),
            "llm_observations": matches.llm_observation_id.nunique(),
            "brands": matches.brand_id.nunique(), "next_step": investigation,
            "evidence": matches,
        })
    return output


def display(value: object) -> str:
    """Keep actual provider codes; unknown is a display label, not a stored value."""
    return "Unknown (not recorded)" if pd.isna(value) else str(value)