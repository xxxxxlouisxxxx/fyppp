select
  cast(llm_target_id as varchar) as llm_target_id,
  {{ nullif_trim('provider') }} as provider,
  {{ nullif_trim('platform') }} as platform,
  {{ nullif_trim('model_name') }} as model,
  cast(active as boolean) as active,
  cast(recorded_at as timestamp) as recorded_at_utc
from {{ source('bronze', 'llm_target_registry') }}