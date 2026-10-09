"""Execute real locale SQL models; never read or modify collected raw artifacts."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment, StrictUndefined

from geo_research.storage import migrations

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_NAMES = (
    "stg_dataforseo__requests",
    "stg_dataforseo__responses",
    "silver_search_observations",
    "silver_llm_observations",
    "silver_serp_items",
    "silver_organic_results",
    "silver_locale_evidence_coverage",
    "gold_brand_organic_hits",
    "gold_serp_brand_visibility",
    "gold_llm_brand_visibility",
    "gold_comparison_brand_metrics",
    "gold_comparison_kpi_summary",
)
SOURCE_TABLES = (
    "bronze.api_requests",
    "bronze.api_responses",
    "bronze.comparison_registry",
    "silver.silver_search_observations",
    "silver.silver_llm_observations",
    "silver.silver_serp_items",
    "silver.silver_organic_results",
)


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    result = connection.execute(sql)
    names = [column[0] for column in result.description]
    return [dict(zip(names, row, strict=True)) for row in result.fetchall()]


def _render_models(connection: duckdb.DuckDBPyConnection) -> None:
    """Use project macros and explicit dbt ref/source relation mappings."""
    refs = {name: f"analytics.{name}" for name in MODEL_NAMES}
    refs.update(
        {
            name: f"analytics.{name}"
            for name in (
                "stg_reference__brands",
                "stg_reference__brand_aliases",
                "stg_reference__brand_domains",
                "stg_reference__comparisons",
            )
        }
    )
    sources = {
        tuple(table.split(".")): table for table in SOURCE_TABLES
    }
    environment = Environment(undefined=StrictUndefined)
    environment.globals.update(
        ref=lambda name: refs[name],
        source=lambda schema, name: sources[(schema, name)],
    )
    macros = "\n".join(
        (PROJECT_ROOT / "macros" / filename).read_text(encoding="utf-8")
        for filename in ("nullif_trim.sql", "normalize_language_code.sql")
    )
    for name in MODEL_NAMES:
        paths = list((PROJECT_ROOT / "models").rglob(f"{name}.sql"))
        assert len(paths) == 1, f"Expected one actual SQL model for {name}"
        template = environment.from_string(
            macros + "\n" + paths[0].read_text(encoding="utf-8")
        )
        connection.execute(f"CREATE TABLE {refs[name]} AS {template.render()}")


def _seed_observation(
    connection: duckdb.DuckDBPyConnection,
    *,
    observation_id: str,
    channel: str,
    target: str,
    language: str | None = "zh_CN",
    location: str | None = " 2344 ",
    window: str = "matched-window",
    received: str = "2026-10-02 12:00:00+00",
    status: str = "available",
    present: bool = True,
) -> None:
    request_id = f"request-{observation_id}"
    response_id = f"response-{observation_id}"
    connection.execute(
        """
        INSERT INTO bronze.api_requests
          (request_id, run_id, source_category, provider, platform, search_engine,
           model_name, request_status, created_at, query_id, collection_window)
        VALUES (?, 'synthetic-run', ?, 'dataforseo', ?, ?, ?, 'completed',
                '2026-10-01 00:00:00+00', ?, ?)
        """,
        [
            request_id, channel, target if channel == "llm" else None,
            target if channel == "serp" else None,
            "test-model" if channel == "llm" else None,
            "prompt-main" if channel == "llm" else "query-main", window,
        ],
    )
    connection.execute(
        """
        INSERT INTO bronze.api_responses
          (response_id, request_id, response_valid, received_at)
        VALUES (?, ?, true, ?)
        """,
        [response_id, request_id, received],
    )
    if channel == "llm":
        connection.execute(
            """
            INSERT INTO silver.silver_llm_observations
              (observation_id, request_id, response_id, provider, platform,
               model_name, query_text, language_code, location_code, items_count,
               response_text, items_json, citations_json, raw_file_hash,
               parser_name, parser_version, outcome_status)
            VALUES (?, ?, ?, 'dataforseo', ?, 'test-model', 'synthetic prompt',
                    ?, ?, 1, ?, '[]', '[]', 'synthetic-hash', 'fixture', '1', ?)
            """,
            [
                observation_id, request_id, response_id, target, language,
                location, "Acme" if present else "No tracked brand", status,
            ],
        )
        return
    connection.execute(
        """
        INSERT INTO silver.silver_search_observations
        VALUES (?, 'query-main', 'dataforseo', ?, 'organic', ?, ?, 'desktop',
                ?, ?, 'synthetic-ingestion', 'synthetic-hash', true, ?)
        """,
        [observation_id, target, location, language, window, response_id, status],
    )
    # Four organic links, exactly one owned link when present: share != presence.
    for rank in range(1, 5):
        item_id = f"item-{observation_id}-{rank}"
        domain = "acme.example" if present and rank == 1 else "other.example"
        url = f"https://{domain}/{rank}"
        connection.execute(
            """
            INSERT INTO silver.silver_serp_items
              (serp_item_id, observation_id, engine, response_id,
               source_ingestion_id, raw_file_hash, item_index, raw_item_type,
               normalized_item_type, normalized_domain, raw_item_json,
               parser_name, parser_version, rank_semantics_version,
               normalization_status)
            VALUES (?, ?, ?, ?, 'synthetic-ingestion', 'synthetic-hash', ?,
                    'organic', 'organic', ?, '{}', 'fixture', '1', '1', 'valid')
            """,
            [item_id, observation_id, target, response_id, rank, domain],
        )
        connection.execute(
            """
            INSERT INTO silver.silver_organic_results
              (organic_result_id, provider, search_engine, search_type,
               observation_id, parent_serp_item_id, source_item_type,
               feature_supported, feature_observed, normalization_status,
               raw_evidence, engine_rank, normalized_rank, raw_url, canonical_url)
            VALUES (?, 'dataforseo', ?, 'organic', ?, ?, 'organic', true, true,
                    'valid', '{}', ?, ?, ?, ?)
            """,
            [f"organic-{item_id}", target, observation_id, item_id,
             rank, rank, url, url],
        )


@pytest.fixture
def locale_models() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect(":memory:") as connection:
        # Keep explicit UTC assertions independent of the host session timezone.
        connection.execute("SET TimeZone = 'UTC'")
        # Exact application source schemas, isolated from every on-disk warehouse.
        for number in range(1, 8):
            connection.execute(getattr(migrations, f"MIGRATION_{number:03d}"))
        connection.execute("CREATE SCHEMA analytics")
        connection.execute(
            """
            CREATE TABLE analytics.stg_reference__brands AS
              SELECT 'acme' AS brand_id, 'Acme' AS canonical_name;
            CREATE TABLE analytics.stg_reference__brand_aliases AS
              SELECT 'acme' AS brand_id, 'Acme' AS alias_text;
            CREATE TABLE analytics.stg_reference__brand_domains AS
              SELECT 'acme' AS brand_id, 'acme.example' AS domain;
            INSERT INTO bronze.comparison_registry VALUES
              ('main', 'query-main', 'prompt-main', true, current_timestamp),
              ('empty', 'query-empty', 'prompt-empty', true, current_timestamp),
              ('inactive', 'query-main', 'prompt-main', false, current_timestamp);
            CREATE TABLE analytics.stg_reference__comparisons AS
              SELECT * FROM bronze.comparison_registry;
            """
        )
        # Opposite lexical orderings catch either ascending or descending ID-based
        # "latest" selection. Old evidence deliberately has opposite presence.
        for channel, targets in (
            ("serp", ("google", "bing")),
            ("llm", ("chatgpt", "gemini")),
        ):
            for index, target in enumerate(targets):
                old_prefix, new_prefix = ("z", "a") if index == 0 else ("a", "z")
                for prefix, age in ((old_prefix, "old"), (new_prefix, "new")):
                    _seed_observation(
                        connection, observation_id=f"{prefix}-{target}-{age}",
                        channel=channel, target=target,
                        language=(
                            "ZH-cn" if age == "old"
                            else "zh_CN" if channel == "serp" else "zh-CN"
                        ),
                        received=("2026-10-02 12:00:00+00" if age == "new"
                                  else "2026-10-02 09:00:00+00"),
                        present=age == "new",
                    )
        for channel, target in (("serp", "google"), ("llm", "chatgpt")):
            _seed_observation(
                connection, observation_id=f"{channel}-region-mismatch",
                channel=channel, target=target, language="en",
                location="2840" if channel == "serp" else "2344",
            )
            _seed_observation(
                connection, observation_id=f"{channel}-language-mismatch",
                channel=channel, target=target,
                language="en" if channel == "serp" else "zh-CN",
                location="2840", window="language-window",
            )
            _seed_observation(
                connection, observation_id=f"{channel}-window-mismatch",
                channel=channel, target=target,
                window=f"{channel}-only-window",
            )
            _seed_observation(
                connection, observation_id=f"{channel}-blank",
                channel=channel, target=target, language="  ", location=" ",
                window="blank-window",
            )
            _seed_observation(
                connection, observation_id=f"{channel}-unavailable",
                channel=channel, target=target, window="unavailable-window",
                status="provider_error",
            )
        _seed_observation(
            connection, observation_id="llm-null", channel="llm",
            target="chatgpt", language=None, location=None, window="null-window",
        )
        before = {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            for table in SOURCE_TABLES
        }
        _render_models(connection)
        yield connection
        # Rendering and all assertions must leave synthetic source/raw evidence
        # byte-for-byte unchanged; this fixture never opens actual raw files.
        for table, original in before.items():
            assert connection.execute(
                f"SELECT * FROM {table} ORDER BY 1"
            ).fetchall() == original, table


def test_silver_normalizes_locale_without_rewriting_raw(locale_models):
    for channel in ("search", "llm"):
        rows = _rows(
            locale_models,
            f"SELECT * FROM analytics.silver_{channel}_observations",
        )
        matched = [row for row in rows if row["observation_id"].endswith("-new")]
        assert len(matched) == 2
        for row in matched:
            assert row["language_code"] == "zh-cn"
            assert row["location_code"] == "2344"
            assert row["raw_language_code"] == (
                "zh_CN" if channel == "search" else "zh-CN"
            )
            assert row["raw_location_code"] == " 2344 "
        blank = next(row for row in rows if row["observation_id"].endswith("-blank"))
        assert blank["language_code"] is None
        assert blank["location_code"] is None
        assert blank["raw_language_code"] == "  "
        assert blank["raw_location_code"] == " "
    null = _rows(
        locale_models,
        "SELECT * FROM analytics.silver_llm_observations "
        "WHERE observation_id = 'llm-null'",
    )[0]
    for field in (
        "language_code", "location_code", "raw_language_code", "raw_location_code"
    ):
        assert null[field] is None


def test_coverage_counts_observations_before_brand_expansion(locale_models):
    counts = dict(locale_models.execute(
        "SELECT source_category, sum(observation_count) "
        "FROM analytics.silver_locale_evidence_coverage GROUP BY source_category"
    ).fetchall())
    for category, relation in (
        ("serp", "silver_search_observations"),
        ("llm", "silver_llm_observations"),
    ):
        assert counts[category] == locale_models.execute(
            f"SELECT count(*) FROM analytics.{relation}"
        ).fetchone()[0]
    assert locale_models.execute(
        "SELECT count(*) FROM analytics.silver_locale_evidence_coverage "
        "WHERE language_code IS NULL AND location_code IS NULL"
    ).fetchone()[0] > 0


def test_collection_timestamps_remain_aware_in_non_utc_session(locale_models):
    locale_models.execute("SET TimeZone = 'Asia/Hong_Kong'")
    environment = Environment(undefined=StrictUndefined)
    environment.globals["source"] = lambda schema, name: f"{schema}.{name}"
    macros = (PROJECT_ROOT / "macros/nullif_trim.sql").read_text(encoding="utf-8")
    model = (
        PROJECT_ROOT / "models/staging/serp/stg_dataforseo__responses.sql"
    ).read_text(encoding="utf-8")
    rows = _rows(locale_models, environment.from_string(macros + model).render())
    for row in rows:
        original = locale_models.execute(
            "SELECT received_at FROM bronze.api_responses WHERE response_id = ?",
            [row["response_id"]],
        ).fetchone()[0]
        assert row["received_at_utc"].tzinfo is not None
        assert row["received_at_utc"] == original


def test_gold_joins_actual_response_time_and_llm_request_window(locale_models):
    for channel in ("serp", "llm"):
        gold = f"analytics.gold_{channel}_brand_visibility"
        rows = _rows(
            locale_models,
            f"""
            SELECT gold.*, response.received_at AS expected_time,
                   request.collection_window AS expected_window,
                   request.query_id AS expected_query
            FROM {gold} gold
            JOIN bronze.api_responses response USING (response_id)
            JOIN bronze.api_requests request ON request.request_id = response.request_id
            """,
        )
        assert len(rows) == locale_models.execute(
            f"SELECT count(*) FROM {gold}"
        ).fetchone()[0]
        for row in rows:
            assert row["collected_at"] == row["expected_time"]
            assert row["collected_at"] != datetime(2026, 10, 1, tzinfo=UTC)
            assert row["collection_window"] == row["expected_window"]
            assert row["raw_file_hash"] == "synthetic-hash"
            if channel == "llm":
                assert row["prompt_id"] == row["expected_query"] == "prompt-main"


def test_latest_timestamp_retains_engine_and_platform_slices(locale_models):
    matched = _rows(
        locale_models,
        "SELECT * FROM analytics.gold_comparison_brand_metrics "
        "WHERE comparison_eligibility = 'matched_context' "
        "AND collection_window = 'matched-window'",
    )
    assert len(matched) == 4
    assert {(row["search_engine"], row["platform"]) for row in matched} == {
        (engine, platform)
        for engine in ("google", "bing")
        for platform in ("chatgpt", "gemini")
    }
    for row in matched:
        assert row["serp_observation_id"].endswith("-new")
        assert row["llm_observation_id"].endswith("-new")
        assert row["serp_collected_at"] == datetime(2026, 10, 2, 12, tzinfo=UTC)
        assert row["llm_collected_at"] == datetime(2026, 10, 2, 12, tzinfo=UTC)
        assert (row["language_code"], row["location_code"]) == ("zh-cn", "2344")


@pytest.mark.parametrize("reason", ["region", "language", "window"])
def test_mismatched_locales_and_windows_never_pair(locale_models, reason):
    rows = _rows(
        locale_models,
        "SELECT * FROM analytics.gold_comparison_brand_metrics "
        f"WHERE serp_observation_id = 'serp-{reason}-mismatch' "
        f"OR llm_observation_id = 'llm-{reason}-mismatch'",
    )
    assert len(rows) == 2
    for row in rows:
        assert row["comparison_eligibility"] == "unmatched_context"
        assert row["availability_status"] == "not_collected"
        assert row["metric_value"] is None
        if row["serp_observation_id"] is None:
            assert row["serp_metric_value"] is None
            assert row["serp_numerator"] is None
            assert row["serp_denominator"] is None
            assert row["llm_metric_value"] == 1
        else:
            assert row["llm_observation_id"] is None
            assert row["llm_metric_value"] is None
            assert row["llm_numerator"] is None
            assert row["llm_denominator"] is None
            assert row["serp_metric_value"] == pytest.approx(0.25)


def test_missing_context_and_approved_no_data_placeholder(locale_models):
    missing = _rows(
        locale_models,
        "SELECT * FROM analytics.gold_comparison_brand_metrics "
        "WHERE collection_window IN ('blank-window', 'null-window')",
    )
    assert len(missing) == 3
    for row in missing:
        assert row["comparison_eligibility"] == "missing_context"
        assert row["metric_value"] is None
        assert row["language_code"] is None
        assert row["location_code"] is None
        assert (row["serp_observation_id"] is None) != (
            row["llm_observation_id"] is None
        )
    empty = _rows(
        locale_models,
        "SELECT * FROM analytics.gold_comparison_brand_metrics "
        "WHERE comparison_id = 'empty'",
    )
    assert len(empty) == 1
    row = empty[0]
    assert row["brand_id"] == "acme"
    assert row["comparison_eligibility"] == "not_collected"
    assert row["availability_status"] == "not_collected"
    for field in (
        "serp_observation_id", "llm_observation_id", "serp_metric_value",
        "llm_metric_value", "metric_value", "language_code", "location_code",
        "collection_window",
    ):
        assert row[field] is None
    assert locale_models.execute(
        "SELECT count(*) FROM analytics.gold_comparison_brand_metrics "
        "WHERE comparison_id = 'inactive'"
    ).fetchone()[0] == 0


def test_presence_gap_is_binary_not_serp_link_share(locale_models):
    rows = _rows(
        locale_models,
        "SELECT * FROM analytics.gold_comparison_kpi_summary "
        "WHERE collection_window = 'matched-window' "
        "AND availability_status = 'available'",
    )
    assert len(rows) == 4
    for row in rows:
        assert (row["serp_numerator"], row["serp_denominator"]) == (1, 4)
        assert row["serp_metric_value"] == pytest.approx(0.25)
        assert row["llm_metric_value"] == 1
        assert row["cross_channel_visibility_gap"] == 0
        assert row["cross_channel_visibility_gap"] != (
            row["llm_metric_value"] - row["serp_metric_value"]
        )
        assert row["serp_presence_flag"] == row["llm_presence_flag"] == 1
        assert row["dual_presence_flag"] == 1
        assert row["blended_visibility_index"] == 1
        assert row["channel_alignment_score"] == 1


def test_metric_and_kpi_ids_unique_and_unavailable_flags_null(locale_models):
    for name, id_column in (
        ("gold_serp_brand_visibility", "metric_id"),
        ("gold_llm_brand_visibility", "metric_id"),
        ("gold_comparison_brand_metrics", "metric_id"),
        ("gold_comparison_kpi_summary", "kpi_id"),
    ):
        count, distinct, nonnull = locale_models.execute(
            f"SELECT count(*), count(DISTINCT {id_column}), count({id_column}) "
            f"FROM analytics.{name}"
        ).fetchone()
        assert count > 0
        assert count == distinct == nonnull
    summary = _rows(
        locale_models, "SELECT * FROM analytics.gold_comparison_kpi_summary"
    )
    metrics = _rows(
        locale_models, "SELECT * FROM analytics.gold_comparison_brand_metrics"
    )
    metrics_by_id = {row["metric_id"]: row for row in metrics}
    assert {row["source_metric_id"] for row in summary} == {
        row["metric_id"] for row in metrics
    }
    for row in summary:
        source = metrics_by_id[row["source_metric_id"]]
        for channel in ("serp", "llm"):
            if source[f"{channel}_availability_status"] != "available":
                assert row[f"{channel}_presence_flag"] is None
        if row["availability_status"] != "available":
            for field in (
                "cross_channel_visibility_gap", "blended_visibility_index",
                "channel_alignment_score", "dual_presence_flag",
            ):
                assert row[field] is None
    unavailable = [
        row for row in summary if row["collection_window"] == "unavailable-window"
    ]
    assert len(unavailable) == 1
    assert unavailable[0]["availability_status"] == "parser_quarantined"
    assert unavailable[0]["comparison_eligibility"] == "matched_context"
    assert unavailable[0]["serp_presence_flag"] is None
    assert unavailable[0]["llm_presence_flag"] is None
    for row in summary:
        if row["comparison_id"] == "empty":
            assert row["serp_presence_flag"] is None
            assert row["llm_presence_flag"] is None