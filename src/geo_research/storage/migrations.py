# ruff: noqa: E501
"""DuckDB Bronze/meta schema migration definitions.

Raw artifacts are finalized before a caller opens a metadata transaction. The
repository writes associated metadata rows in one transaction, so a failed
commit leaves detectable unreferenced raw evidence rather than partial rows.
"""

from __future__ import annotations

MIGRATION_009 = """
CREATE TABLE IF NOT EXISTS silver.evidence_results_v2 (
 result_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL,
 request_id VARCHAR, response_id VARCHAR, raw_file_hash VARCHAR,
 source_category VARCHAR, provider VARCHAR, engine_or_platform VARCHAR,
 query_id VARCHAR, query_text VARCHAR, language_code VARCHAR, location_code VARCHAR,
 device VARCHAR, os VARCHAR, request_depth BIGINT, collected_at TIMESTAMPTZ,
 provider_result_datetime VARCHAR, task_id VARCHAR, task_index INTEGER,
 result_index INTEGER, json_path VARCHAR, check_url VARCHAR, model_name VARCHAR,
 collection_status VARCHAR, top_level_item_count BIGINT, provider_reported_item_count BIGINT,
 parsed_top_level_item_count BIGINT, parse_success_rate DOUBLE,
 issues_json VARCHAR, enrichment_version VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.evidence_items_v2 (
 item_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL, result_id VARCHAR NOT NULL,
 parent_item_id VARCHAR, json_path VARCHAR, is_top_level BOOLEAN,
 item_kind VARCHAR, raw_item_type VARCHAR, title VARCHAR, description VARCHAR,
 url VARCHAR, domain VARCHAR, rank_group BIGINT, rank_absolute BIGINT,
 organic_rank BIGINT, page_position BIGINT, normalized_text VARCHAR,
 text_method VARCHAR, coverage_status VARCHAR, raw_evidence_json VARCHAR,
 enrichment_version VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.evidence_features_v2 (
 feature_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL, result_id VARCHAR NOT NULL,
 feature VARCHAR, coverage_status VARCHAR, observed_count BIGINT,
 exhaustive_count BIGINT, issues_json VARCHAR, enrichment_version VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.evidence_citations_v2 (
 citation_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL, result_id VARCHAR NOT NULL,
 canonical_url VARCHAR, domain VARCHAR, enrichment_version VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.evidence_citation_occurrences_v2 (
 occurrence_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL, result_id VARCHAR NOT NULL,
 citation_id VARCHAR, item_id VARCHAR, parent_item_id VARCHAR, json_path VARCHAR,
 raw_url VARCHAR, enrichment_version VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.evidence_matches_v2 (
 evidence_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL, result_id VARCHAR NOT NULL,
 item_id VARCHAR, citation_id VARCHAR, identity_id VARCHAR, identity_name VARCHAR,
 identity_type VARCHAR, review_status VARCHAR, evidence_type VARCHAR,
 matched_field VARCHAR, matched_text VARCHAR, span_start INTEGER, span_end INTEGER,
 method VARCHAR, registry_version VARCHAR, enrichment_version VARCHAR
);
"""

MIGRATION_008 = """
CREATE SCHEMA IF NOT EXISTS silver;
CREATE TABLE IF NOT EXISTS silver.silver_response_summaries (
    observation_id VARCHAR PRIMARY KEY, source_category VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL, response_id VARCHAR NOT NULL,
    raw_file_hash VARCHAR NOT NULL, query_id VARCHAR, query_text VARCHAR,
    provider VARCHAR, engine_or_platform VARCHAR, model_name VARCHAR,
    language_code VARCHAR, location_code VARCHAR, collected_at TIMESTAMPTZ,
    task_id VARCHAR, status_code INTEGER,
    collection_status VARCHAR, evidence_coverage_status VARCHAR NOT NULL,
    brand_coverage_status VARCHAR NOT NULL, category_coverage_status VARCHAR NOT NULL,
    provider_reported_item_count BIGINT, top_level_item_count BIGINT,
    atomic_item_count BIGINT, organic_count BIGINT, product_card_count BIGINT,
    answer_block_count BIGINT, image_count BIGINT, citation_count BIGINT,
    distinct_brand_count BIGINT, brand_ids VARCHAR[], brand_names VARCHAR[],
    answer_brand_ids VARCHAR[], cited_brand_ids VARCHAR[], result_types VARCHAR[],
    business_categories VARCHAR[], issues_json VARCHAR NOT NULL,
    enrichment_version VARCHAR NOT NULL, registry_version VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS silver.silver_response_items (
    item_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL,
    parent_item_id VARCHAR, json_path VARCHAR NOT NULL, item_kind VARCHAR NOT NULL,
    raw_item_type VARCHAR, raw_evidence_json VARCHAR NOT NULL,
    coverage_status VARCHAR NOT NULL, enrichment_version VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS silver.silver_item_brand_evidence (
    evidence_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL,
    item_id VARCHAR NOT NULL, brand_id VARCHAR NOT NULL, brand_name VARCHAR NOT NULL,
    evidence_type VARCHAR NOT NULL, matched_field VARCHAR NOT NULL,
    matched_text VARCHAR NOT NULL, span_start INTEGER, span_end INTEGER,
    method VARCHAR NOT NULL, method_version VARCHAR NOT NULL,
    registry_version VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS silver.silver_item_category_evidence (
    evidence_id VARCHAR PRIMARY KEY, observation_id VARCHAR NOT NULL,
    item_id VARCHAR NOT NULL, category_id VARCHAR NOT NULL,
    category_name VARCHAR NOT NULL,
    matched_field VARCHAR NOT NULL, matched_text VARCHAR NOT NULL,
    method VARCHAR NOT NULL, taxonomy_version VARCHAR NOT NULL,
    rule_id VARCHAR NOT NULL,
    rule_version VARCHAR NOT NULL
);
"""

MIGRATION_001 = """
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS meta;
CREATE TABLE IF NOT EXISTS meta.schema_migrations (
    migration_id VARCHAR PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze.ingestion_runs (
    run_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS bronze.query_registry (
    query_id VARCHAR PRIMARY KEY, keyword VARCHAR NOT NULL, active BOOLEAN NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze.search_target_registry (
    search_target_id VARCHAR PRIMARY KEY, provider VARCHAR NOT NULL,
    search_engine VARCHAR NOT NULL, search_type VARCHAR NOT NULL,
    model_name VARCHAR, active BOOLEAN NOT NULL, recorded_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze.llm_prompt_registry (
    prompt_id VARCHAR PRIMARY KEY,
    prompt_group VARCHAR NOT NULL,
    active BOOLEAN NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze.llm_target_registry (
    llm_target_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    platform VARCHAR NOT NULL,
    model_name VARCHAR NOT NULL,
    active BOOLEAN NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze.comparison_registry (
    comparison_id VARCHAR PRIMARY KEY,
    query_id VARCHAR NOT NULL,
    prompt_id VARCHAR NOT NULL,
    active BOOLEAN NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze.api_requests (
    request_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,
    source_category VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    platform VARCHAR,
    search_engine VARCHAR,
    model_name VARCHAR,
    request_status VARCHAR NOT NULL,
    estimated_cost DOUBLE,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze.api_attempts (
    attempt_id VARCHAR PRIMARY KEY,
    request_id VARCHAR NOT NULL,
    attempt_number INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    transport_status VARCHAR NOT NULL,
    UNIQUE(request_id, attempt_number)
);
CREATE TABLE IF NOT EXISTS bronze.api_responses (
    response_id VARCHAR PRIMARY KEY, request_id VARCHAR NOT NULL UNIQUE,
    provider_request_id VARCHAR, response_valid BOOLEAN NOT NULL, actual_cost DOUBLE,
    received_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze.raw_files (
    raw_file_id VARCHAR PRIMARY KEY,
    request_id VARCHAR NOT NULL,
    artifact_type VARCHAR NOT NULL,
    raw_directory VARCHAR NOT NULL,
    relative_path VARCHAR NOT NULL UNIQUE,
    sha256 VARCHAR NOT NULL,
    byte_size BIGINT NOT NULL,
    content_type VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(request_id, artifact_type)
);
"""

MIGRATION_002 = """
CREATE SCHEMA IF NOT EXISTS silver;
CREATE TABLE IF NOT EXISTS silver.silver_search_observations (
    observation_id VARCHAR PRIMARY KEY,
    query_id VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    search_engine VARCHAR NOT NULL,
    search_type VARCHAR NOT NULL,
    location_code VARCHAR NOT NULL,
    language_code VARCHAR NOT NULL,
    device VARCHAR NOT NULL,
    collection_window VARCHAR NOT NULL,
    response_id VARCHAR NOT NULL,
    source_ingestion_id VARCHAR NOT NULL,
    raw_file_hash VARCHAR NOT NULL,
    has_results BOOLEAN NOT NULL,
    outcome_status VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS silver.silver_serp_items (
    serp_item_id VARCHAR PRIMARY KEY,
    observation_id VARCHAR NOT NULL,
    engine VARCHAR NOT NULL,
    response_id VARCHAR NOT NULL,
    source_ingestion_id VARCHAR NOT NULL,
    raw_file_hash VARCHAR NOT NULL,
    item_index INTEGER NOT NULL,
    raw_item_type VARCHAR,
    normalized_item_type VARCHAR NOT NULL,
    rank_group INTEGER,
    rank_absolute INTEGER,
    page INTEGER,
    position INTEGER,
    raw_domain VARCHAR,
    normalized_domain VARCHAR,
    raw_url VARCHAR,
    canonical_url VARCHAR,
    title VARCHAR,
    description VARCHAR,
    raw_item_json VARCHAR NOT NULL,
    parser_name VARCHAR NOT NULL,
    parser_version VARCHAR NOT NULL,
    rank_semantics_version VARCHAR NOT NULL,
    normalization_status VARCHAR NOT NULL,
    parsing_warning VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.silver_serp_parsing_quarantine (
    quarantine_id VARCHAR PRIMARY KEY,
    observation_id VARCHAR NOT NULL,
    engine VARCHAR NOT NULL,
    response_id VARCHAR NOT NULL,
    source_ingestion_id VARCHAR NOT NULL,
    raw_file_hash VARCHAR NOT NULL,
    item_index INTEGER,
    reason VARCHAR NOT NULL,
    raw_item_json VARCHAR,
    parser_name VARCHAR NOT NULL,
    parser_version VARCHAR NOT NULL
);
"""

MIGRATION_003 = """
CREATE TABLE IF NOT EXISTS silver.silver_organic_results (
    organic_result_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    search_engine VARCHAR NOT NULL,
    search_type VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    parent_serp_item_id VARCHAR NOT NULL,
    source_item_type VARCHAR,
    feature_supported BOOLEAN NOT NULL,
    feature_observed BOOLEAN NOT NULL,
    normalization_status VARCHAR NOT NULL,
    raw_evidence VARCHAR NOT NULL,
    engine_rank INTEGER NOT NULL,
    normalized_rank INTEGER NOT NULL,
    raw_url VARCHAR,
    canonical_url VARCHAR,
    title VARCHAR,
    description VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.silver_paid_results (
    paid_result_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    search_engine VARCHAR NOT NULL,
    search_type VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    parent_serp_item_id VARCHAR NOT NULL,
    source_item_type VARCHAR,
    feature_supported BOOLEAN NOT NULL,
    feature_observed BOOLEAN NOT NULL,
    normalization_status VARCHAR NOT NULL,
    raw_evidence VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS silver.silver_local_results (
    local_result_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    search_engine VARCHAR NOT NULL,
    search_type VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    parent_serp_item_id VARCHAR NOT NULL,
    source_item_type VARCHAR,
    feature_supported BOOLEAN NOT NULL,
    feature_observed BOOLEAN NOT NULL,
    normalization_status VARCHAR NOT NULL,
    raw_evidence VARCHAR NOT NULL,
    business_name VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.silver_question_results (
    question_result_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    search_engine VARCHAR NOT NULL,
    search_type VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    parent_serp_item_id VARCHAR NOT NULL,
    source_item_type VARCHAR,
    feature_supported BOOLEAN NOT NULL,
    feature_observed BOOLEAN NOT NULL,
    normalization_status VARCHAR NOT NULL,
    raw_evidence VARCHAR NOT NULL,
    question_text VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.silver_related_queries (
    related_query_result_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    search_engine VARCHAR NOT NULL,
    search_type VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    parent_serp_item_id VARCHAR NOT NULL,
    source_item_type VARCHAR,
    feature_supported BOOLEAN NOT NULL,
    feature_observed BOOLEAN NOT NULL,
    normalization_status VARCHAR NOT NULL,
    raw_evidence VARCHAR NOT NULL,
    recommendation VARCHAR
);
CREATE TABLE IF NOT EXISTS silver.silver_image_results (
    image_result_id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    search_engine VARCHAR NOT NULL,
    search_type VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    parent_serp_item_id VARCHAR NOT NULL,
    source_item_type VARCHAR,
    feature_supported BOOLEAN NOT NULL,
    feature_observed BOOLEAN NOT NULL,
    normalization_status VARCHAR NOT NULL,
    raw_evidence VARCHAR NOT NULL,
    image_url VARCHAR
);
"""

MIGRATION_004 = """
ALTER TABLE bronze.api_requests ADD COLUMN IF NOT EXISTS query_id VARCHAR;
ALTER TABLE bronze.api_requests ADD COLUMN IF NOT EXISTS search_target_id VARCHAR;
ALTER TABLE bronze.api_requests ADD COLUMN IF NOT EXISTS collection_window VARCHAR;
ALTER TABLE bronze.api_requests ADD COLUMN IF NOT EXISTS request_hash VARCHAR;
ALTER TABLE bronze.api_requests ADD COLUMN IF NOT EXISTS deduplication_key VARCHAR;
ALTER TABLE bronze.api_responses ADD COLUMN IF NOT EXISTS task_id VARCHAR;
"""

MIGRATION_005 = """
CREATE SCHEMA IF NOT EXISTS silver;
CREATE TABLE IF NOT EXISTS silver.silver_llm_observations (
    observation_id VARCHAR PRIMARY KEY,
    request_id VARCHAR NOT NULL,
    response_id VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    platform VARCHAR NOT NULL,
    model_name VARCHAR NOT NULL,
    query_text VARCHAR,
    task_id VARCHAR,
    status_code INTEGER,
    cost DOUBLE,
    language_code VARCHAR,
    location_code VARCHAR,
    items_count INTEGER NOT NULL,
    response_text VARCHAR,
    items_json VARCHAR NOT NULL,
    citations_json VARCHAR NOT NULL,
    raw_file_hash VARCHAR NOT NULL,
    parser_name VARCHAR NOT NULL,
    parser_version VARCHAR NOT NULL,
    outcome_status VARCHAR NOT NULL
);
"""

MIGRATION_006 = """
CREATE SCHEMA IF NOT EXISTS presentation;
CREATE TABLE IF NOT EXISTS presentation.releases (
    release_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    metric_version VARCHAR NOT NULL,
    notes VARCHAR,
    completeness_json VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS presentation.release_current (
    slot VARCHAR PRIMARY KEY,
    release_id VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS presentation.release_serp_brand_visibility (
    release_id VARCHAR NOT NULL,
    metric_id VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    query_id VARCHAR NOT NULL,
    brand_id VARCHAR NOT NULL,
    brand_canonical_name VARCHAR,
    provider VARCHAR,
    search_engine VARCHAR,
    search_type VARCHAR,
    collection_window VARCHAR,
    source_category VARCHAR NOT NULL,
    metric_name VARCHAR NOT NULL,
    metric_version VARCHAR NOT NULL,
    numerator BIGINT NOT NULL,
    denominator BIGINT NOT NULL,
    metric_value DOUBLE,
    availability_status VARCHAR NOT NULL,
    collection_status VARCHAR NOT NULL,
    has_results BOOLEAN,
    best_normalized_rank INTEGER,
    response_id VARCHAR,
    raw_file_hash VARCHAR,
    PRIMARY KEY (release_id, metric_id)
);
CREATE TABLE IF NOT EXISTS presentation.release_llm_brand_visibility (
    release_id VARCHAR NOT NULL,
    metric_id VARCHAR NOT NULL,
    observation_id VARCHAR NOT NULL,
    prompt_id VARCHAR,
    brand_id VARCHAR NOT NULL,
    brand_canonical_name VARCHAR,
    provider VARCHAR,
    platform VARCHAR,
    model_name VARCHAR,
    source_category VARCHAR NOT NULL,
    metric_name VARCHAR NOT NULL,
    metric_version VARCHAR NOT NULL,
    numerator BIGINT NOT NULL,
    denominator BIGINT NOT NULL,
    metric_value DOUBLE,
    availability_status VARCHAR NOT NULL,
    collection_status VARCHAR NOT NULL,
    mention_count BIGINT,
    citation_count BIGINT,
    request_id VARCHAR,
    response_id VARCHAR,
    raw_file_hash VARCHAR,
    PRIMARY KEY (release_id, metric_id)
);
CREATE TABLE IF NOT EXISTS presentation.release_comparison_brand_metrics (
    release_id VARCHAR NOT NULL,
    metric_id VARCHAR NOT NULL,
    comparison_id VARCHAR NOT NULL,
    query_id VARCHAR NOT NULL,
    prompt_id VARCHAR NOT NULL,
    brand_id VARCHAR NOT NULL,
    brand_canonical_name VARCHAR,
    metric_name VARCHAR NOT NULL,
    metric_version VARCHAR NOT NULL,
    serp_observation_id VARCHAR,
    llm_observation_id VARCHAR,
    serp_availability_status VARCHAR NOT NULL,
    llm_availability_status VARCHAR NOT NULL,
    serp_collection_status VARCHAR,
    llm_collection_status VARCHAR,
    serp_numerator BIGINT,
    serp_denominator BIGINT,
    serp_metric_value DOUBLE,
    llm_numerator BIGINT,
    llm_denominator BIGINT,
    llm_metric_value DOUBLE,
    metric_value DOUBLE,
    availability_status VARCHAR NOT NULL,
    PRIMARY KEY (release_id, metric_id)
);
"""

MIGRATION_007 = """
ALTER TABLE presentation.release_serp_brand_visibility
    ADD COLUMN IF NOT EXISTS language_code VARCHAR;
ALTER TABLE presentation.release_serp_brand_visibility
    ADD COLUMN IF NOT EXISTS location_code VARCHAR;
ALTER TABLE presentation.release_serp_brand_visibility
    ADD COLUMN IF NOT EXISTS raw_language_code VARCHAR;
ALTER TABLE presentation.release_serp_brand_visibility
    ADD COLUMN IF NOT EXISTS raw_location_code VARCHAR;
ALTER TABLE presentation.release_serp_brand_visibility
    ADD COLUMN IF NOT EXISTS device VARCHAR;
ALTER TABLE presentation.release_serp_brand_visibility
    ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ;
ALTER TABLE presentation.release_llm_brand_visibility
    ADD COLUMN IF NOT EXISTS language_code VARCHAR;
ALTER TABLE presentation.release_llm_brand_visibility
    ADD COLUMN IF NOT EXISTS location_code VARCHAR;
ALTER TABLE presentation.release_llm_brand_visibility
    ADD COLUMN IF NOT EXISTS raw_language_code VARCHAR;
ALTER TABLE presentation.release_llm_brand_visibility
    ADD COLUMN IF NOT EXISTS raw_location_code VARCHAR;
ALTER TABLE presentation.release_llm_brand_visibility
    ADD COLUMN IF NOT EXISTS collection_window VARCHAR;
ALTER TABLE presentation.release_llm_brand_visibility
    ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS language_code VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS location_code VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS serp_provider VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS search_engine VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS search_type VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS device VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS llm_provider VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS platform VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS model_name VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS collection_window VARCHAR;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS serp_collected_at TIMESTAMPTZ;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS llm_collected_at TIMESTAMPTZ;
ALTER TABLE presentation.release_comparison_brand_metrics
    ADD COLUMN IF NOT EXISTS comparison_eligibility VARCHAR;
"""
