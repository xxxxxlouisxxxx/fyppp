select
  cast(metrics.release_id as varchar) as release_id,
  cast(metrics.metric_id as varchar) as metric_id,
  cast(metrics.observation_id as varchar) as observation_id,
  cast(metrics.query_id as varchar) as query_id,
  cast(metrics.brand_id as varchar) as brand_id,
  {{ nullif_trim('metrics.brand_canonical_name') }} as brand_canonical_name,
  {{ nullif_trim('metrics.provider') }} as provider,
  {{ nullif_trim('metrics.search_engine') }} as search_engine,
  {{ nullif_trim('metrics.search_type') }} as search_type,
  {{ nullif_trim('metrics.collection_window') }} as collection_window,
  {{ nullif_trim('metrics.source_category') }} as source_category,
  {{ nullif_trim('metrics.metric_name') }} as metric_name,
  {{ nullif_trim('metrics.metric_version') }} as metric_version,
  cast(metrics.numerator as bigint) as numerator,
  cast(metrics.denominator as bigint) as denominator,
  cast(metrics.metric_value as double) as metric_value,
  {{ nullif_trim('metrics.availability_status') }} as availability_status,
  {{ nullif_trim('metrics.collection_status') }} as collection_status,
  cast(metrics.has_results as boolean) as has_results,
  cast(metrics.best_normalized_rank as integer) as best_normalized_rank,
  cast(metrics.response_id as varchar) as response_id,
  {{ nullif_trim('metrics.raw_file_hash') }} as raw_file_hash,
  metrics.language_code,
  metrics.location_code,
  metrics.raw_language_code,
  metrics.raw_location_code,
  metrics.device,
  cast(metrics.collected_at as timestamptz) as collected_at
from {{ source('presentation', 'release_serp_brand_visibility') }} as metrics
inner join {{ source('presentation', 'release_current') }} as current_slot
  on current_slot.release_id = metrics.release_id
  and current_slot.slot = 'current'
inner join {{ source('presentation', 'releases') }} as releases
  on releases.release_id = current_slot.release_id
  and releases.status = 'completed'
