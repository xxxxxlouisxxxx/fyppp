with organic as (
  select
    organic.organic_result_id,
    organic.observation_id,
    organic.parent_serp_item_id,
    organic.search_engine,
    organic.search_type,
    organic.normalized_rank,
    organic.canonical_url,
    organic.raw_url,
    lower(coalesce(items.normalized_domain, '')) as normalized_domain
  from {{ ref('silver_organic_results') }} as organic
  left join {{ ref('silver_serp_items') }} as items
    on items.serp_item_id = organic.parent_serp_item_id
),
domains as (
  select
    brand_id,
    lower(trim(domain)) as normalized_domain
  from {{ ref('stg_reference__brand_domains') }}
  where domain is not null
)
select
  organic.organic_result_id,
  organic.observation_id,
  organic.parent_serp_item_id,
  organic.search_engine,
  organic.search_type,
  organic.normalized_rank,
  organic.canonical_url,
  organic.raw_url,
  organic.normalized_domain,
  domains.brand_id
from organic
inner join domains
  on domains.normalized_domain = organic.normalized_domain
