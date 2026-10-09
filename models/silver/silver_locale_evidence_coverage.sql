-- Count observations before the observation x brand expansion in Gold.
with observations as (
  select
    'serp' as source_category,
    observation.query_id as instrument_id,
    observation.provider,
    observation.search_engine as platform,
    cast(null as varchar) as model_name,
    observation.language_code,
    observation.location_code,
    observation.device,
    observation.collection_window,
    observation.observation_id,
    observation.outcome_status,
    responses.received_at_utc as collected_at
  from {{ ref('silver_search_observations') }} as observation
  left join {{ ref('stg_dataforseo__responses') }} as responses
    on responses.response_id = observation.response_id
  union all
  select
    'llm', requests.query_id, observation.provider, observation.platform,
    observation.model_name, observation.language_code, observation.location_code,
    cast(null as varchar), requests.collection_window_id,
    observation.observation_id, observation.outcome_status,
    responses.received_at_utc
  from {{ ref('silver_llm_observations') }} as observation
  left join {{ ref('stg_dataforseo__requests') }} as requests
    on requests.request_id = observation.request_id
    and requests.source_category = 'llm'
  left join {{ ref('stg_dataforseo__responses') }} as responses
    on responses.response_id = observation.response_id
)
select
  source_category, instrument_id, provider, platform, model_name,
  language_code, location_code, device, collection_window,
  coalesce(outcome_status, 'not_collected') as collection_status,
  count(distinct observation_id) as observation_count,
  min(collected_at) as first_collected_at,
  max(collected_at) as last_collected_at
from observations
group by all