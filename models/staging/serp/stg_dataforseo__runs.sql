select
  cast(run_id as varchar) as run_id,
  {{ nullif_trim('status') }} as outcome_status,
  case
    when lower({{ nullif_trim('status') }}) in ('completed', 'partial_success') then true
    when {{ nullif_trim('status') }} is null then null
    else false
  end as collection_success,
  cast(started_at as timestamp) as started_at_utc,
  cast(completed_at as timestamp) as completed_at_utc
from {{ source('bronze', 'ingestion_runs') }}
