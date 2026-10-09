select
  cast(query_id as varchar) as query_id,
  {{ nullif_trim('keyword') }} as keyword,
  cast(active as boolean) as active,
  cast(recorded_at as timestamp) as recorded_at_utc
from {{ source('bronze', 'query_registry') }}