with observations as (
  select
    llm.observation_id,
    llm.request_id,
    llm.response_id,
    llm.provider,
    llm.platform,
    llm.model_name,
    llm.language_code,
    llm.location_code,
    llm.raw_language_code,
    llm.raw_location_code,
    requests.collection_window_id as collection_window,
    responses.received_at_utc as collected_at,
    llm.query_text,
    llm.items_count,
    -- Retained raw subtrees are additive Silver evidence, not new legacy hits.
    cast((
      select json_group_array(json_merge_patch(
        value, '{"raw_item":null,"result_sources":null,"json_path":null}'
      ))
      from json_each(llm.items_json)
    ) as varchar) as items_json,
    llm.citations_json,
    llm.response_text,
    llm.raw_file_hash,
    llm.outcome_status,
    requests.query_id as prompt_id
  from {{ ref('silver_llm_observations') }} as llm
  left join {{ ref('stg_dataforseo__requests') }} as requests
    on requests.request_id = llm.request_id
    and requests.source_category = 'llm'
  left join {{ ref('stg_dataforseo__responses') }} as responses
    on responses.response_id = llm.response_id
),
aliases as (
  select
    brands.brand_id,
    brands.canonical_name,
    lower(trim(aliases.alias_text)) as alias_text
  from {{ ref('stg_reference__brand_aliases') }} as aliases
  inner join {{ ref('stg_reference__brands') }} as brands
    on brands.brand_id = aliases.brand_id
  where aliases.alias_text is not null
),
citation_domains as (
  select
    brands.brand_id,
    brands.canonical_name,
    lower(trim(domains.domain)) as normalized_domain
  from {{ ref('stg_reference__brand_domains') }} as domains
  inner join {{ ref('stg_reference__brands') }} as brands
    on brands.brand_id = domains.brand_id
  where domains.domain is not null
),
mention_hits as (
  select
    observations.observation_id,
    aliases.brand_id,
    count(*) as mention_count
  from observations
  inner join aliases
    on (
      strpos(lower(coalesce(observations.response_text, '')), aliases.alias_text) > 0
      or strpos(lower(coalesce(observations.items_json, '')), aliases.alias_text) > 0
    )
  group by observations.observation_id, aliases.brand_id
),
citation_hits as (
  select
    observations.observation_id,
    citation_domains.brand_id,
    count(*) as citation_count
  from observations
  inner join citation_domains
    on strpos(lower(coalesce(observations.citations_json, '')), citation_domains.normalized_domain) > 0
  group by observations.observation_id, citation_domains.brand_id
),
brands as (
  select brand_id, canonical_name
  from {{ ref('stg_reference__brands') }}
),
grain as (
  select
    observations.observation_id,
    observations.prompt_id,
    observations.request_id,
    observations.response_id,
    observations.provider,
    observations.platform,
    observations.model_name,
    observations.language_code,
    observations.location_code,
    observations.raw_language_code,
    observations.raw_location_code,
    observations.collection_window,
    observations.collected_at,
    observations.items_count,
    observations.raw_file_hash,
    observations.outcome_status,
    brands.brand_id,
    brands.canonical_name,
    coalesce(mention_hits.mention_count, 0) as mention_count,
    coalesce(citation_hits.citation_count, 0) as citation_count
  from observations
  cross join brands
  left join mention_hits
    on mention_hits.observation_id = observations.observation_id
    and mention_hits.brand_id = brands.brand_id
  left join citation_hits
    on citation_hits.observation_id = observations.observation_id
    and citation_hits.brand_id = brands.brand_id
)
select
  md5(
    concat_ws(
      '|',
      observation_id,
      brand_id,
      'llm_brand_mention',
      '1.0.0'
    )
  ) as metric_id,
  observation_id,
  prompt_id,
  brand_id,
  canonical_name as brand_canonical_name,
  provider,
  platform,
  model_name,
  'llm' as source_category,
  'llm_brand_mention' as metric_name,
  '1.0.0' as metric_version,
  mention_count as numerator,
  case
    when outcome_status = 'available' then greatest(items_count, 1)
    else 0
  end as denominator,
  case
    when outcome_status = 'available' then (mention_count > 0)::int::double
    else null
  end as metric_value,
  case
    when outcome_status = 'available' and items_count > 0 then 'available'
    when outcome_status = 'available' and items_count = 0 then 'no_results'
    when outcome_status is null then 'not_collected'
    else outcome_status
  end as availability_status,
  outcome_status as collection_status,
  mention_count,
  citation_count,
  request_id,
  response_id,
  raw_file_hash,
  language_code,
  location_code,
  raw_language_code,
  raw_location_code,
  collection_window,
  collected_at
from grain
