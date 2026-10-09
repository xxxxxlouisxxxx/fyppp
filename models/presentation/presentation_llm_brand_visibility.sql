select
  cast(metrics.release_id as varchar) as release_id,
  cast(metrics.metric_id as varchar) as metric_id,
  cast(metrics.observation_id as varchar) as observation_id,
  cast(metrics.prompt_id as varchar) as prompt_id,
  cast(metrics.brand_id as varchar) as brand_id,
  {{ nullif_trim('metrics.brand_canonical_name') }} as brand_canonical_name,
  {{ nullif_trim('metrics.provider') }} as provider,
  {{ nullif_trim('metrics.platform') }} as platform,
  {{ nullif_trim('metrics.model_name') }} as model_name,
  {{ nullif_trim('metrics.source_category') }} as source_category,
  {{ nullif_trim('metrics.metric_name') }} as metric_name,
  {{ nullif_trim('metrics.metric_version') }} as metric_version,
  cast(metrics.numerator as bigint) as numerator,
  cast(metrics.denominator as bigint) as denominator,
  cast(metrics.metric_value as double) as metric_value,
  {{ nullif_trim('metrics.availability_status') }} as availability_status,
  {{ nullif_trim('metrics.collection_status') }} as collection_status,
  cast(metrics.mention_count as bigint) as mention_count,
  cast(metrics.citation_count as bigint) as citation_count,
  cast(metrics.request_id as varchar) as request_id,
  cast(metrics.response_id as varchar) as response_id,
  {{ nullif_trim('metrics.raw_file_hash') }} as raw_file_hash,
  metrics.language_code,
  metrics.location_code,
  metrics.raw_language_code,
  metrics.raw_location_code,
  metrics.collection_window,
  cast(metrics.collected_at as timestamptz) as collected_at
from {{ source('presentation', 'release_llm_brand_visibility') }} as metrics
inner join {{ source('presentation', 'release_current') }} as current_slot
  on current_slot.release_id = metrics.release_id
  and current_slot.slot = 'current'
inner join {{ source('presentation', 'releases') }} as releases
  on releases.release_id = current_slot.release_id
  and releases.status = 'completed'
