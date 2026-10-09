with base as (
  select
    metric_id,
    comparison_id,
    query_id,
    prompt_id,
    brand_id,
    brand_canonical_name,
    serp_numerator,
    serp_denominator,
    serp_metric_value,
    llm_numerator,
    llm_denominator,
    llm_metric_value,
    metric_value as cross_channel_visibility_gap,
    availability_status,
    language_code,
    location_code,
    serp_provider,
    search_engine,
    search_type,
    device,
    llm_provider,
    platform,
    model_name,
    collection_window,
    serp_collected_at,
    llm_collected_at,
    comparison_eligibility,
    case
      when serp_availability_status = 'available' and serp_numerator is not null
        then (serp_numerator > 0)::int
      else null
    end as serp_presence_flag,
    case
      when llm_availability_status = 'available' and llm_metric_value is not null
        then (llm_metric_value > 0)::int
      else null
    end as llm_presence_flag
  from {{ ref('gold_comparison_brand_metrics') }}
)
select
  md5(to_json(list_value(metric_id, 'comparison_kpi_summary', '2.0.0'))) as kpi_id,
  metric_id as source_metric_id,
  comparison_id,
  query_id,
  prompt_id,
  brand_id,
  brand_canonical_name,
  'comparison_kpi_summary' as kpi_name,
  '2.0.0' as kpi_version,
  serp_numerator,
  serp_denominator,
  serp_metric_value,
  llm_numerator,
  llm_denominator,
  llm_metric_value,
  cross_channel_visibility_gap,
  -- Legacy column names retained; these are exploratory binary-presence
  -- descriptors, not validated visibility/traffic scores or Top10 measures.
  case
    when availability_status = 'available'
      then (serp_presence_flag + llm_presence_flag) / 2.0
    else null
  end as blended_visibility_index,
  case
    when availability_status = 'available'
      then 1.0 - abs(llm_presence_flag - serp_presence_flag)
    else null
  end as channel_alignment_score,
  serp_presence_flag,
  llm_presence_flag,
  case
    when availability_status = 'available'
      then serp_presence_flag * llm_presence_flag
    else null
  end as dual_presence_flag,
  availability_status,
  language_code,
  location_code,
  serp_provider,
  search_engine,
  search_type,
  device,
  llm_provider,
  platform,
  model_name,
  collection_window,
  serp_collected_at,
  llm_collected_at,
  comparison_eligibility
from base
