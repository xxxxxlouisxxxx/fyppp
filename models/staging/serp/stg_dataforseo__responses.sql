select
  cast(response_id as varchar) as response_id,
  cast(request_id as varchar) as request_id,
  {{ nullif_trim('provider_request_id') }} as provider_request_id,
  {{ nullif_trim('task_id') }} as task_id,
  cast(response_valid as boolean) as response_valid,
  cast(null as boolean) as has_results,
  case
    when cast(response_valid as boolean) = true then 'available'
    when cast(response_valid as boolean) = false then 'provider_error'
    else 'not_applicable'
  end as outcome_status,
  cast(actual_cost as double) as actual_cost_usd,
  cast(received_at as timestamptz) as received_at_utc,
  cast(null as varchar) as response_json,
  cast(null as varchar) as source_api_version,
  cast(null as varchar) as adapter_version
from {{ source('bronze', 'api_responses') }}
