select gold.metric_id
from {{ ref('gold_serp_brand_visibility') }} as gold
join {{ ref('silver_search_observations') }} as silver
  on silver.observation_id = gold.observation_id
where gold.language_code is distinct from silver.language_code
  or gold.location_code is distinct from silver.location_code
  or gold.raw_language_code is distinct from silver.raw_language_code
  or gold.raw_location_code is distinct from silver.raw_location_code
union all
select gold.metric_id
from {{ ref('gold_llm_brand_visibility') }} as gold
join {{ ref('silver_llm_observations') }} as silver
  on silver.observation_id = gold.observation_id
where gold.language_code is distinct from silver.language_code
  or gold.location_code is distinct from silver.location_code
  or gold.raw_language_code is distinct from silver.raw_language_code
  or gold.raw_location_code is distinct from silver.raw_location_code