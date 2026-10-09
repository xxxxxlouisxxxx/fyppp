"""Streamlit release explorer. All interaction operates on a frozen snapshot."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from geo_research.dashboard.data import (
    Filters,
    display,
    eligible_comparisons,
    filtered,
    load_snapshot,
    locale_summary,
    opportunities,
    presence_summary,
    research_summary,
    source_statuses,
)
from geo_research.storage.reviews import history

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COLORS = {"SERP": "#2563eb", "LLM": "#7c3aed"}
LIMITATIONS = (
    "Exploratory observed presence, not traffic, demand, causality or ROI. "
    "SERP presence means at least one matched owned organic result, not Top10. "
    "LLM presence uses the existing alias/serialized-item matcher: it is not "
    "validated answer-only mention extraction. Mention/citation counts count "
    "matching registry entries, not true occurrences or unique citations. "
    "Unknown locale stays unknown; provider location identifiers are not "
    "verified applied personalization. Collection timestamps are receive times."
)


def _options(frames: dict[str, pd.DataFrame], column: str) -> list:
    values = pd.concat([f[column] for f in frames.values() if column in f])
    known = sorted(set(values.dropna().astype(str)))
    return known + ([None] if values.isna().any() else [])


def _select(label: str, values: list, key: str) -> tuple | None:
    chosen = st.sidebar.multiselect(
        label, values, default=values, format_func=display, key=key,
    )
    # All selected is unrestricted, including legacy unknown source contexts.
    return None if len(chosen) == len(values) else tuple(chosen)


def _table(frame: pd.DataFrame) -> None:
    st.dataframe(frame, hide_index=True, width="stretch")


def main() -> None:
    st.set_page_config(
        page_title="Presence Atlas · Release Explorer", page_icon="◈", layout="wide",
    )
    st.markdown(
        """<style>
        .stApp {background: #f8fafc; color: #172554;}
        [data-testid="stSidebar"] {background: #eef2ff;}
        [data-testid="stMetric"] {background: white; border: 1px solid #dbeafe;
          border-radius: 16px; padding: 18px;}
        h1, h2, h3 {color: #1e3a8a;}
        .atlas-header {background: linear-gradient(115deg,#1d4ed8,#7c3aed);
          border-radius: 20px; padding: 26px 32px; color: white; margin-bottom: 24px;}
        .atlas-header h1 {color: white; margin: 0; font-size: 2.2rem;}
            [data-baseweb="tag"] {background-color: #2563eb !important;}
            button[role="tab"][aria-selected="true"] {color: #2563eb;}
            </style>"""
            '<div class="atlas-header"><h1>Presence Atlas</h1>'
            '<p>Completed-release research · '
            'SERP &amp; generative visibility</p></div>',
        unsafe_allow_html=True,
    )
    st.sidebar.title("Release explorer")
    database = st.sidebar.text_input(
        "Existing DuckDB warehouse",
        value=os.environ.get(
            "GEO_DASHBOARD_DB",
            str(PROJECT_ROOT / "data/warehouse/geo_research.duckdb"),
        ),
    )
    initial = load_snapshot(database)
    ids = initial.releases.release_id.tolist() if not initial.releases.empty else []
    selection = st.sidebar.selectbox(
        "Completed release", [None, *ids],
        format_func=lambda value: "Current pointer" if value is None else value,
    )
    snapshot = initial if selection is None else load_snapshot(database, selection)
    st.sidebar.caption("Read only · No API collection · No database migrations")
    if snapshot.message:
        st.info(snapshot.message)
        st.caption(
            "Existing releases only. "
            "Publishing or collecting is outside this dashboard."
        )
        return
    record = snapshot.release
    st.caption(
        f"Frozen release: {record['release_id']} "
        f"· Created: {display(record['created_at'])} "
        f"· Completed: {display(record['completed_at'])} "
        f"· Release metadata version: {record['metric_version']} "
        "(individual metric versions govern interpretation)"
    )
    with st.expander("Data limitations & metric definitions", expanded=False):
        st.write(LIMITATIONS)
        st.write(
            "Channel presence rate = distinct available observation-brand rows with "
            "presence / distinct available observation-brand rows. Counts are shown "
            "per brand. Source status counts deduplicate observations across brands. "
            "Unsupported metric versions are retained in Evidence, not summarized."
        )
    frames = snapshot.frames
    filters = Filters(
        brands=_select("Brand ID", _options(frames, "brand_id"), "brands"),
        languages=_select(
            "Language code", _options(frames, "language_code"), "languages",
        ),
        locations=_select(
            "Provider location identifier",
            _options(frames, "location_code"), "locations",
        ),
        windows=_select(
            "Collection window", _options(frames, "collection_window"), "windows",
        ),
        engines=_select("SERP engine", _options(frames, "search_engine"), "engines"),
        platforms=_select("LLM platform", _options(frames, "platform"), "platforms"),
    )
    st.sidebar.caption(
        "Engine applies only to SERP; platform only to LLM. Both apply to "
        "comparison pairs. Empty selection excludes that channel's rows."
    )
    frames = filtered(snapshot, filters)
    summary = presence_summary(frames)
    # Research rows are frozen to this release; filters follow channel observations.
    observed_ids = (
        set(frames["serp"].observation_id) | set(frames["llm"].observation_id)
    )
    research = {}
    for kind, original in snapshot.research.items():
        local = original.copy()
        if "observation_id" in local:
            local = local[local.observation_id.isin(observed_ids)]
        if filters.brands is not None and "brand_id" in local:
            local = local[local.brand_id.isin(filters.brands)]
        research[kind] = local
    metrics = research.get("metrics", pd.DataFrame())
    v2_summary = research_summary(metrics)
    tabs = st.tabs([
        "Overview", "Need × Market Map", "Brand Competition",
        "Evidence & Citation Explorer", "Opportunity Queue",
    ])
    with tabs[0]:
        if "coverage" in research:
            st.subheader("Frozen feature coverage · experimental")
            st.caption(
                "Feature absence and collection status are separate; "
                "no benchmark validation implied."
            )
            _table(research["coverage"])
        st.subheader("Observed channel presence")
        statuses = source_statuses(frames)
        cols = st.columns(3)
        for col, channel in zip(cols[:2], ("SERP", "LLM"), strict=True):
            total = statuses.loc[statuses.channel.eq(channel), "observations"].sum()
            col.metric(f"{channel} distinct observations", int(total))
        cols[2].metric(
            "Eligible matched-context pairs",
            len(eligible_comparisons(frames["comparison"])),
        )
        if summary.empty:
            st.info("No channel evidence matches these filters.")
        else:
            chart = px.bar(
                summary, x="brand_id", y="presence_rate", color="channel",
                barmode="group", color_discrete_map=COLORS,
                hover_data=["brand", "present", "available", "unavailable"],
                labels={
                    "presence_rate": "Available observation presence rate",
                    "brand_id": "Brand",
                },
            )
            chart.update_yaxes(range=[0, 1], tickformat=".0%")
            st.plotly_chart(chart, width="stretch")
            _table(summary)
        st.caption("Unobserved/unavailable evidence is never counted as brand absence.")
        st.subheader("Source & collection status")
        _table(statuses)
    with tabs[1]:
        st.subheader("Locale × brand evidence map")
        needs = research.get("needs", pd.DataFrame())
        if not needs.empty and not metrics.empty:
            st.subheader("Explicit approved-rule need × locale evidence")
            st.caption(
                "Multilabel rule matches; experimental extraction, "
                "not independent samples across needs."
            )
            _table(needs.merge(metrics, on="result_id", how="inner"))
        else:
            st.info(
            "Approved need taxonomy/mapping snapshots are not available in this "
            "release contract. Need-level patterns are unavailable, not inferred "
            "from query or prompt text. The legacy locale map remains exploratory."
            )
        st.warning(
            "Instrument-mix warning: locales may contain different queries/prompts, "
            "engines, platforms, models, devices and sample sizes. This is not a "
            "controlled region/language effect. Location labels preserve provider IDs."
        )
        markets = locale_summary(frames)
        if markets.empty:
            st.info("No locale evidence matches these filters.")
        else:
            markets["scope"] = (
                markets.channel + " | " + markets.instrument + " | window="
                + markets.collection_window.map(display)
            )
            scope = st.selectbox(
                "Instrument / window slice", sorted(markets.scope.unique()),
            )
            local = markets[markets.scope.eq(scope)]
            matrix = local.pivot(
                index="locale", columns="brand_id", values="presence_rate",
            )
            if matrix.notna().any().any():
                chart = px.imshow(
                    matrix, zmin=0, zmax=1, aspect="auto",
                    color_continuous_scale=["#eff6ff", "#2563eb", "#7c3aed"],
                    labels={"color": "Presence rate"},
                )
                st.plotly_chart(chart, width="stretch")
            else:
                st.info(
                    "This slice has no available observations; rates remain unknown."
                )
            _table(local.drop(columns="scope"))
    with tabs[2]:
        st.subheader("Brand competition · observed samples")
        if not v2_summary.empty:
            st.subheader("Independent feature presence · experimental")
            _table(v2_summary)
            st.caption(
                "Item/unique-URL shares use full observed denominators, including "
                "unattributed and ambiguous entities; no market HHI claim."
            )
            _table(metrics)
        st.warning(
            "Legacy metrics are exploratory. Formal approved-brand v2 metrics "
            "require the independent registry/extraction publication gates. "
            "These samples are not total market demand or market concentration."
        )
        _table(summary)
        serp = frames["serp"]
        available = serp[
            serp.metric_name.eq("serp_organic_sov")
            & serp.metric_version.eq("1.0.0")
            & serp.availability_status.eq("available")
            & serp.denominator.gt(0)
        ].drop_duplicates(["observation_id", "brand_id"])
        st.caption(
            "Organic item share per observation is separate from observation "
            "presence rate; no approved-only renormalization or HHI market claim."
        )
        _table(available[[
            "brand_id", "observation_id", "numerator", "denominator", "metric_value",
        ]].rename(columns={"metric_value": "organic_item_share"}))
    with tabs[3]:
        st.subheader("Snapshot evidence & lineage")
        mappings = research.get("mappings", pd.DataFrame())
        if not mappings.empty:
            with st.expander("Frozen instrument mapping approvals"):
                _table(mappings)
        if snapshot.evidence.empty:
            st.info("No approved original snippets or citation URLs in this release.")
        else:
            ids = set(frames["serp"].metric_id) | set(frames["llm"].metric_id)
            approved = snapshot.evidence[snapshot.evidence.metric_id.isin(ids)]
            st.caption(
                "Original approved source fields copied at publication, not live "
                "raw reads. Display approval does not validate extraction/KPIs. "
                "Citation URL rows are evidence, not a computed citation share."
            )
            _table(approved)
        channel = st.selectbox("Evidence channel", ["serp", "llm", "comparison"])
        evidence = frames[channel]
        st.caption(
            "Snapshot fields only: observation/query/prompt IDs, metric versions, "
            "statuses, context and lineage. "
            "No raw answer text, URLs or invented snippets."
        )
        _table(evidence)
        if not evidence.empty:
            metric_id = st.selectbox(
                "Drill down metric ID", evidence.metric_id.tolist(),
            )
            selected = evidence[evidence.metric_id.eq(metric_id)]
            st.write(f"Definition contract: {display(selected.iloc[0].metric_name)}")
            definitions = {
                "serp_organic_sov": (
                    "v1: matched owned organic slots / observed organic slots. "
                    "The dashboard derives binary presence from numerator > 0."
                ),
                "llm_brand_mention": (
                    "v1: binary existing alias-match presence. Numerator counts "
                    "matching alias entries; denominator is not a presence-rate sample."
                ),
                "comparison_brand_presence": (
                    "v2 only: binary LLM presence minus binary owned-organic SERP "
                    "presence in available matched context; not a commercial score."
                ),
            }
            st.write(definitions.get(
                selected.iloc[0].metric_name,
                "Legacy or unsupported metric: retained as evidence, not interpreted.",
            ))
            _table(selected.T.map(display).rename(
                columns={selected.index[0]: "Snapshot value"},
            ))
            st.caption(
                "Raw hashes are lineage identifiers, not links to fetched raw content."
            )
    with tabs[4]:
        candidates = research.get("candidates", pd.DataFrame())
        if not candidates.empty:
            st.subheader("Result-driven entity review candidates")
            st.caption(
                "No preselected brand required. Candidate names do not establish "
                "identity, ownership or formal KPIs."
            )
            _table(candidates)
        st.subheader("Exploratory investigation patterns")
        st.caption(
            "Available v2 matched-context rows only. Binary SERP/LLM indicators, "
            "not link-share subtraction, a priority score or an ROI prediction. "
            "Source pairs can reuse observations; "
            "pair counts are not independent samples."
        )
        patterns = opportunities(frames["comparison"])
        for column, pattern in zip(st.columns(3), patterns, strict=True):
            with column, st.container(border=True):
                st.markdown(f"### {pattern['title']}")
                st.metric("Context/source pairs", pattern["pairs"])
                st.caption(
                    f"{pattern['serp_observations']} distinct SERP · "
                    f"{pattern['llm_observations']} distinct LLM · "
                    f"{pattern['brands']} brands"
                )
                st.write(pattern["next_step"])
                with st.expander("Pair evidence"):
                    _table(pattern["evidence"])
        eligible = eligible_comparisons(frames["comparison"])
        both = int((eligible.serp_present & eligible.llm_present).sum())
        st.caption(f"Both present: {both} pairs (context, not an opportunity signal).")
        if eligible.empty:
            st.info(
                "No eligible v2 pairs. Legacy v1, unknown context "
                "and unavailable rows are excluded."
            )
        st.subheader("Manual review & next actions · read-only history")
        review_path = st.text_input(
            "Existing separate review store (.sqlite)",
            value=os.environ.get("GEO_REVIEW_STORE", ""),
        )
        st.caption(
            "Action entry uses the separate controlled review command, never "
            "this snapshot consumer. Workflow status does not upgrade evidence "
            "classification. Reviewer, reason and release references are required."
        )
        if review_path:
            try:
                events = pd.DataFrame(history(Path(review_path)))
                if events.empty:
                    st.info("No review events; no store was created.")
                else:
                    events = events[events.release_id.eq(record["release_id"])]
                    _table(events)
            except (sqlite3.Error, OSError):
                st.warning(
                    "Cannot read the existing review store; no data was changed."
                )
    st.divider()
    st.caption(
        "Research evidence only · Validate matching, sample coverage "
        "and business relevance independently."
    )