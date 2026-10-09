with comparisons as (
  select
    comparison_id,
    query_id,
    prompt_id
  from {{ ref('stg_reference__comparisons') }}
  where active = true
),
brands as (
  select
    brand_id,
    canonical_name
  from {{ ref('stg_reference__brands') }}
),
serp_latest as (
  select *
  from (
    select
      serp.*,
      row_number() over (
        partition by
          serp.query_id, serp.brand_id, serp.provider, serp.search_engine,
          serp.search_type, serp.device, serp.language_code, serp.location_code,
          serp.collection_window
        order by serp.collected_at desc nulls last, serp.observation_id
      ) as row_rank
    from {{ ref('gold_serp_brand_visibility') }} as serp
  ) ranked
  where row_rank = 1
),
llm_latest as (
  select *
  from (
    select
      llm.*,
      row_number() over (
        partition by
          llm.prompt_id, llm.brand_id, llm.provider, llm.platform, llm.model_name,
          llm.language_code, llm.location_code, llm.collection_window
        order by llm.collected_at desc nulls last, llm.observation_id
      ) as row_rank
    from {{ ref('gold_llm_brand_visibility') }} as llm
  ) ranked
  where row_rank = 1
),
approved_grain as (
  select
    comparisons.comparison_id,
    comparisons.query_id,
    comparisons.prompt_id,
    brands.brand_id,
    brands.canonical_name
  from comparisons
  cross join brands
),
mapped_serp as (
  select approved.comparison_id, serp.*
  from approved_grain as approved
  inner join serp_latest as serp
    on serp.query_id = approved.query_id
    and serp.brand_id = approved.brand_id
),
mapped_llm as (
  select approved.comparison_id, llm.*
  from approved_grain as approved
  inner join llm_latest as llm
    on llm.prompt_id = approved.prompt_id
    and llm.brand_id = approved.brand_id
),
paired_contexts as (
  select
    coalesce(serp.comparison_id, llm.comparison_id) as comparison_id,
    coalesce(serp.brand_id, llm.brand_id) as brand_id,
    serp.observation_id as serp_observation_id,
    llm.observation_id as llm_observation_id,
    serp.availability_status as serp_availability_status,
    llm.availability_status as llm_availability_status,
    serp.collection_status as serp_collection_status,
    llm.collection_status as llm_collection_status,
    serp.numerator as serp_numerator,
    serp.denominator as serp_denominator,
    serp.metric_value as serp_metric_value,
    llm.numerator as llm_numerator,
    llm.denominator as llm_denominator,
    llm.metric_value as llm_metric_value,
    coalesce(serp.language_code, llm.language_code) as language_code,
    coalesce(serp.location_code, llm.location_code) as location_code,
    serp.raw_language_code as serp_raw_language_code,
    serp.raw_location_code as serp_raw_location_code,
    llm.raw_language_code as llm_raw_language_code,
    llm.raw_location_code as llm_raw_location_code,
    serp.provider as serp_provider,
    serp.search_engine,
    serp.search_type,
    serp.device,
    llm.provider as llm_provider,
    llm.platform,
    llm.model_name,
    coalesce(serp.collection_window, llm.collection_window) as collection_window,
    serp.collected_at as serp_collected_at,
    llm.collected_at as llm_collected_at
  from mapped_serp as serp
  full outer join mapped_llm as llm
    on serp.comparison_id = llm.comparison_id
    and serp.brand_id = llm.brand_id
    -- Only normalized, known locale and explicit equal windows permit pairing.
    -- Source slices may pair within that context, never across locales/windows.
    and serp.language_code is not null and llm.language_code is not null
    and serp.language_code = llm.language_code
    and serp.location_code is not null and llm.location_code is not null
    and serp.location_code = llm.location_code
    and serp.collection_window is not null and llm.collection_window is not null
    and serp.collection_window = llm.collection_window
),
grain as (
  select
    approved.query_id,
    approved.prompt_id,
    approved.canonical_name,
    approved.comparison_id,
    approved.brand_id,
    paired.* exclude (comparison_id, brand_id),
    case
      when paired.serp_observation_id is null and paired.llm_observation_id is null
        then 'not_collected'
      when paired.language_code is null or paired.location_code is null
        or paired.collection_window is null then 'missing_context'
      when paired.serp_observation_id is not null and paired.llm_observation_id is not null
        then 'matched_context'
      else 'unmatched_context'
    end as comparison_eligibility
  from approved_grain as approved
  -- A no-observation placeholder exists only when neither mapped channel has rows.
  left join paired_contexts as paired
    on paired.comparison_id = approved.comparison_id
    and paired.brand_id = approved.brand_id
)
select
  md5(
    -- Positional JSON preserves nulls and escapes delimiters in source values.
    to_json(list_value(
      comparison_id,
      brand_id,
      serp_observation_id,
      llm_observation_id,
      cast(language_code as varchar),
      cast(location_code as varchar),
      cast(serp_raw_language_code as varchar),
      cast(serp_raw_location_code as varchar),
      cast(llm_raw_language_code as varchar),
      cast(llm_raw_location_code as varchar),
      serp_provider, search_engine, search_type, device,
      llm_provider, platform, model_name,
      cast(collection_window as varchar),
      'comparison_brand_presence',
      '2.0.0'
    ))
  ) as metric_id,
  comparison_id,
  query_id,
  prompt_id,
  brand_id,
  canonical_name as brand_canonical_name,
  'comparison_brand_presence' as metric_name,
  '2.0.0' as metric_version,
  serp_observation_id,
  llm_observation_id,
  coalesce(serp_availability_status, 'not_collected') as serp_availability_status,
  coalesce(llm_availability_status, 'not_collected') as llm_availability_status,
  serp_collection_status,
  llm_collection_status,
  serp_numerator,
  serp_denominator,
  serp_metric_value,
  llm_numerator,
  llm_denominator,
  llm_metric_value,
  -- Exploratory binary LLM presence minus observed owned-organic SERP presence.
  -- This is NOT Top10 presence: a validated collection depth is unavailable.
  -- Retain the original link-share and LLM metrics above as channel evidence.
  case
    when comparison_eligibility = 'matched_context'
      and serp_availability_status = 'available'
      and llm_availability_status = 'available'
      and serp_numerator is not null and llm_metric_value is not null
      then (llm_metric_value > 0)::int - (serp_numerator > 0)::int
    else null
  end as metric_value,
  case
    when comparison_eligibility = 'matched_context'
      and serp_availability_status = 'available'
      and llm_availability_status = 'available'
      and serp_numerator is not null and llm_metric_value is not null
      then 'available'
    when coalesce(serp_availability_status, 'not_collected') in (
      'parser_quarantined', 'provider_error', 'quarantined'
    ) or coalesce(llm_availability_status, 'not_collected') in (
      'parser_quarantined', 'provider_error', 'quarantined'
    ) then 'parser_quarantined'
    when coalesce(serp_availability_status, 'not_collected') = 'no_results'
      or coalesce(llm_availability_status, 'not_collected') = 'no_results'
      then 'no_results'
    when serp_observation_id is null or llm_observation_id is null
      then 'not_collected'
    else 'not_applicable'
  end as availability_status,
  language_code,
  location_code,
  serp_provider,
  search_engine,
  search_type,
  device,
  llm_provider,
  platform,
  model_name,
  collection_window,
  serp_collected_at,
  llm_collected_at,
  comparison_eligibility
from grain
