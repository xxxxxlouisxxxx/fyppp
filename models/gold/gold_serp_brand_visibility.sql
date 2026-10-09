with observations as (
  select
    observation.observation_id,
    observation.query_id,
    observation.provider,
    observation.search_engine,
    observation.search_type,
    observation.collection_window,
    observation.language_code,
    observation.location_code,
    observation.raw_language_code,
    observation.raw_location_code,
    observation.device,
    responses.received_at_utc as collected_at,
    observation.has_results,
    observation.outcome_status,
    observation.response_id,
    observation.raw_file_hash
  from {{ ref('silver_search_observations') }} as observation
  left join {{ ref('stg_dataforseo__responses') }} as responses
    on responses.response_id = observation.response_id
),
organic_counts as (
  select
    observation_id,
    count(*) as organic_result_count
  from {{ ref('silver_organic_results') }}
  group by observation_id
),
brand_hits as (
  select
    observation_id,
    brand_id,
    count(*) as brand_organic_count,
    min(normalized_rank) as best_normalized_rank
  from {{ ref('gold_brand_organic_hits') }}
  group by observation_id, brand_id
),
brands as (
  select brand_id, canonical_name
  from {{ ref('stg_reference__brands') }}
),
grain as (
  select
    observations.observation_id,
    observations.query_id,
    observations.provider,
    observations.search_engine,
    observations.search_type,
    observations.collection_window,
    observations.language_code,
    observations.location_code,
    observations.raw_language_code,
    observations.raw_location_code,
    observations.device,
    observations.collected_at,
    observations.has_results,
    observations.outcome_status,
    observations.response_id,
    observations.raw_file_hash,
    brands.brand_id,
    brands.canonical_name,
    coalesce(organic_counts.organic_result_count, 0) as organic_result_count,
    coalesce(brand_hits.brand_organic_count, 0) as brand_organic_count,
    brand_hits.best_normalized_rank
  from observations
  cross join brands
  left join organic_counts
    on organic_counts.observation_id = observations.observation_id
  left join brand_hits
    on brand_hits.observation_id = observations.observation_id
    and brand_hits.brand_id = brands.brand_id
)
select
  md5(
    concat_ws(
      '|',
      observation_id,
      brand_id,
      'serp_organic_sov',
      '1.0.0'
    )
  ) as metric_id,
  observation_id,
  query_id,
  brand_id,
  canonical_name as brand_canonical_name,
  provider,
  search_engine,
  search_type,
  collection_window,
  'serp' as source_category,
  'serp_organic_sov' as metric_name,
  '1.0.0' as metric_version,
  brand_organic_count as numerator,
  organic_result_count as denominator,
  case
    when outcome_status = 'available' and organic_result_count > 0
      then brand_organic_count::double / organic_result_count::double
    else null
  end as metric_value,
  case
    when outcome_status = 'available' and organic_result_count > 0 then 'available'
    when outcome_status = 'available' and organic_result_count = 0 then 'no_results'
    when outcome_status is null then 'not_collected'
    else outcome_status
  end as availability_status,
  outcome_status as collection_status,
  has_results,
  best_normalized_rank,
  response_id,
  raw_file_hash,
  language_code,
  location_code,
  raw_language_code,
  raw_location_code,
  device,
  collected_at
from grain
