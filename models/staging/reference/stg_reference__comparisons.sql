select
  cast(comparison_id as varchar) as comparison_id,
  cast(query_id as varchar) as query_id,
  cast(prompt_id as varchar) as prompt_id,
  cast(active as boolean) as active,
  cast(recorded_at as timestamp) as recorded_at_utc
from {{ source('bronze', 'comparison_registry') }}