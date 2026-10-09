select
  cast(search_target_id as varchar) as search_target_id,
  {{ nullif_trim('provider') }} as provider,
  lower({{ nullif_trim('search_engine') }}) as search_engine,
  {{ nullif_trim('search_type') }} as search_type,
  {{ nullif_trim('model_name') }} as model_name,
  cast(active as boolean) as active,
  cast(recorded_at as timestamp) as recorded_at_utc,
  cast(null as varchar) as endpoint_name,
  cast(null as varchar) as retrieval_method
from {{ source('bronze', 'search_target_registry') }}