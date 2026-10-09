select
  cast(metrics.release_id as varchar) as release_id,
  cast(metrics.metric_id as varchar) as metric_id,
  cast(metrics.comparison_id as varchar) as comparison_id,
  cast(metrics.query_id as varchar) as query_id,
  cast(metrics.prompt_id as varchar) as prompt_id,
  cast(metrics.brand_id as varchar) as brand_id,
  {{ nullif_trim('metrics.brand_canonical_name') }} as brand_canonical_name,
  {{ nullif_trim('metrics.metric_name') }} as metric_name,
  {{ nullif_trim('metrics.metric_version') }} as metric_version,
  cast(metrics.serp_observation_id as varchar) as serp_observation_id,
  cast(metrics.llm_observation_id as varchar) as llm_observation_id,
  {{ nullif_trim('metrics.serp_availability_status') }} as serp_availability_status,
  {{ nullif_trim('metrics.llm_availability_status') }} as llm_availability_status,
  {{ nullif_trim('metrics.serp_collection_status') }} as serp_collection_status,
  {{ nullif_trim('metrics.llm_collection_status') }} as llm_collection_status,
  cast(metrics.serp_numerator as bigint) as serp_numerator,
  cast(metrics.serp_denominator as bigint) as serp_denominator,
  cast(metrics.serp_metric_value as double) as serp_metric_value,
  cast(metrics.llm_numerator as bigint) as llm_numerator,
  cast(metrics.llm_denominator as bigint) as llm_denominator,
  cast(metrics.llm_metric_value as double) as llm_metric_value,
  cast(metrics.metric_value as double) as metric_value,
  {{ nullif_trim('metrics.availability_status') }} as availability_status,
  metrics.language_code,
  metrics.location_code,
  metrics.serp_provider,
  metrics.search_engine,
  metrics.search_type,
  metrics.device,
  metrics.llm_provider,
  metrics.platform,
  metrics.model_name,
  metrics.collection_window,
  cast(metrics.serp_collected_at as timestamptz) as serp_collected_at,
  cast(metrics.llm_collected_at as timestamptz) as llm_collected_at,
  metrics.comparison_eligibility
from {{ source('presentation', 'release_comparison_brand_metrics') }} as metrics
inner join {{ source('presentation', 'release_current') }} as current_slot
  on current_slot.release_id = metrics.release_id
  and current_slot.slot = 'current'
inner join {{ source('presentation', 'releases') }} as releases
  on releases.release_id = current_slot.release_id
  and releases.status = 'completed'
