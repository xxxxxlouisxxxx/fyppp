select
  cast(request_id as varchar) as request_id,
  cast(run_id as varchar) as run_id,
  {{ nullif_trim('source_category') }} as source_category,
  {{ nullif_trim('provider') }} as provider,
  {{ nullif_trim('search_engine') }} as search_engine,
  cast(null as varchar) as search_type,
  {{ nullif_trim('platform') }} as platform,
  {{ nullif_trim('model_name') }} as model_name,
  {{ nullif_trim('request_status') }} as outcome_status,
  case
    when lower({{ nullif_trim('request_status') }}) in ('completed', 'partial_success') then true
    when {{ nullif_trim('request_status') }} is null then null
    else false
  end as collection_success,
  cast(estimated_cost as double) as estimated_cost_usd,
  cast(created_at as timestamptz) as created_at_utc,
  cast(null as varchar) as endpoint_name,
  cast(null as varchar) as serp_function,
  cast(null as varchar) as retrieval_method,
  cast(null as varchar) as ingestion_id,
  {{ nullif_trim('request_hash') }} as request_hash,
  {{ nullif_trim('deduplication_key') }} as deduplication_key,
  {{ nullif_trim('collection_window') }} as collection_window_id,
  {{ nullif_trim('query_id') }} as query_id,
  cast(null as varchar) as source_api_version,
  cast(null as varchar) as adapter_version
from {{ source('bronze', 'api_requests') }}
