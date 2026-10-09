with base as (
  select
    observation_id,
    request_id,
    response_id,
    provider,
    platform,
    model_name,
    query_text,
    items_count,
    response_text,
    citations_json,
    raw_file_hash,
    outcome_status
  from {{ ref('silver_llm_observations') }}
)
select
  md5(concat_ws('|', observation_id, 'llm_observation_kpi', '1.0.0')) as measure_id,
  observation_id,
  request_id,
  response_id,
  provider,
  platform,
  model_name,
  query_text,
  'llm_observation_kpi' as kpi_name,
  '1.0.0' as kpi_version,
  coalesce(items_count, 0) as items_count,
  coalesce(
    json_array_length(try_cast(citations_json as json)),
    0
  ) as citation_count,
  length(coalesce(response_text, '')) as response_text_length,
  case
    when outcome_status = 'available' and coalesce(items_count, 0) > 0 then 'available'
    when outcome_status = 'available' and coalesce(items_count, 0) = 0 then 'no_results'
    when outcome_status is null then 'not_collected'
    else outcome_status
  end as availability_status,
  outcome_status as collection_status,
  raw_file_hash
from base
