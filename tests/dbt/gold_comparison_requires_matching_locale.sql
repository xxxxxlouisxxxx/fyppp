select comparison.metric_id
from {{ ref('gold_comparison_brand_metrics') }} as comparison
left join {{ ref('gold_serp_brand_visibility') }} as serp
  on serp.observation_id = comparison.serp_observation_id
  and serp.brand_id = comparison.brand_id
left join {{ ref('gold_llm_brand_visibility') }} as llm
  on llm.observation_id = comparison.llm_observation_id
  and llm.brand_id = comparison.brand_id
where comparison.comparison_eligibility = 'matched_context'
  and (
    serp.observation_id is null or llm.observation_id is null
    or serp.language_code is null or llm.language_code is null
    or serp.location_code is null or llm.location_code is null
    or serp.collection_window is null or llm.collection_window is null
    or serp.language_code <> llm.language_code
    or serp.location_code <> llm.location_code
    or serp.collection_window <> llm.collection_window
  )