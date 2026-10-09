select
  cast(prompt_id as varchar) as prompt_id,
  {{ nullif_trim('prompt_group') }} as prompt_group,
  cast(active as boolean) as active,
  cast(recorded_at as timestamp) as recorded_at_utc
from {{ source('bronze', 'llm_prompt_registry') }}