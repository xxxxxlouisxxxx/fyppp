select
  cast(attempt_id as varchar) as attempt_id,
  cast(request_id as varchar) as request_id,
  cast(attempt_number as integer) as attempt_number,
  cast(started_at as timestamp) as started_at_utc,
  cast(ended_at as timestamp) as ended_at_utc,
  {{ nullif_trim('transport_status') }} as transport_status
from {{ source('bronze', 'api_attempts') }}
