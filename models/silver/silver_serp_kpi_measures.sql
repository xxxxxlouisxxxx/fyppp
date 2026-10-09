with base as (
  select
    observation_id,
    query_id,
    provider,
    search_engine,
    search_type,
    collection_window,
    has_results,
    outcome_status
  from {{ ref('silver_search_observations') }}
),
serp_items as (
  select
    observation_id,
    count(*) as serp_item_count
  from {{ ref('silver_serp_items') }}
  group by observation_id
),
organic_results as (
  select
    observation_id,
    count(*) as organic_result_count
  from {{ ref('silver_organic_results') }}
  group by observation_id
),
quarantine as (
  select
    observation_id,
    count(*) as quarantine_count
  from {{ ref('silver_serp_parsing_quarantine') }}
  group by observation_id
)
select
  md5(concat_ws('|', base.observation_id, 'serp_observation_kpi', '1.0.0')) as measure_id,
  base.observation_id,
  base.query_id,
  base.provider,
  base.search_engine,
  base.search_type,
  base.collection_window,
  'serp_observation_kpi' as kpi_name,
  '1.0.0' as kpi_version,
  coalesce(serp_items.serp_item_count, 0) as serp_item_count,
  coalesce(organic_results.organic_result_count, 0) as organic_result_count,
  coalesce(quarantine.quarantine_count, 0) as quarantine_count,
  base.has_results,
  case
    when (coalesce(serp_items.serp_item_count, 0) + coalesce(quarantine.quarantine_count, 0)) > 0
      then coalesce(serp_items.serp_item_count, 0)::double
        / (
          coalesce(serp_items.serp_item_count, 0)
          + coalesce(quarantine.quarantine_count, 0)
        )::double
    else null
  end as parse_success_rate,
  case
    when coalesce(serp_items.serp_item_count, 0) > 0
      then coalesce(organic_results.organic_result_count, 0)::double
        / coalesce(serp_items.serp_item_count, 0)::double
    else null
  end as organic_coverage_rate,
  case
    when base.outcome_status = 'available' and coalesce(serp_items.serp_item_count, 0) > 0 then 'available'
    when base.outcome_status = 'available' and coalesce(serp_items.serp_item_count, 0) = 0 then 'no_results'
    when base.outcome_status is null then 'not_collected'
    else base.outcome_status
  end as availability_status,
  base.outcome_status as collection_status
from base
left join serp_items
  on serp_items.observation_id = base.observation_id
left join organic_results
  on organic_results.observation_id = base.observation_id
left join quarantine
  on quarantine.observation_id = base.observation_id
