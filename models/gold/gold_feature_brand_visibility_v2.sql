-- Independent v2 channel measures; never changes the legacy dashboard models.
with eligible_brands as (
  select * from {{ source('bronze', 'brand_registry') }}
  where active and lower(ownership_type) in ('owned', 'competitor')
    and not regexp_matches(lower(canonical_name), 'to_be_verified|example|placeholder|sanitized|範例|示例')
), grain as (
  select r.*, b.brand_id, b.canonical_name, f.feature, f.coverage_status,
    f.observed_count as observed_channel_count, f.exhaustive_count as exhaustive_channel_count
  from {{ ref('silver_evidence_results_v2') }} r
  join {{ ref('silver_feature_coverage_v2') }} f using (result_id)
  cross join eligible_brands b
  where (b.effective_start_date is null or cast(r.collected_at as date) >= b.effective_start_date)
    and (b.effective_end_date is null or cast(r.collected_at as date) <= b.effective_end_date)
), counts as (
  select g.result_id, g.brand_id, g.feature,
    count(distinct case when g.feature='answer_text' and m.evidence_type='answer_text'
      then m.item_id || ':' || m.matched_field || ':' || m.span_start || ':' || m.span_end end) as mentions,
    count(distinct case when g.feature='citation' and m.evidence_type='owned_citation' then m.citation_id end) as citations,
    count(distinct case when g.feature='organic' and m.evidence_type='owned_organic' then m.item_id
      when g.feature='paid' and m.evidence_type='paid_domain' and i.is_top_level then m.item_id
      when g.feature='product' and m.evidence_type='product_text' then m.item_id end) as slots,
    min(case when g.feature='organic' and m.evidence_type='owned_organic' then i.organic_rank end) as best_organic_rank
  from grain g
  left join {{ ref('silver_feature_matches_v2') }} m
    on m.result_id=g.result_id and m.identity_id=g.brand_id
    and m.identity_type='brand' and m.review_status='approved'
  left join {{ ref('silver_readable_items_v2') }} i on i.item_id=m.item_id
  group by g.result_id, g.brand_id, g.feature
), measured as (
  select g.*, c.best_organic_rank,
    case when g.coverage_status not in ('complete', 'partial') then null
      when g.feature='answer_text' then c.mentions when g.feature='citation' then c.citations else c.slots end as observed_brand_count
  from grain g join counts c using (result_id, brand_id, feature)
)
select *, '2.0.0' as metric_version,
  case when coverage_status='complete' then observed_brand_count end as exhaustive_brand_count,
  case when observed_brand_count>0 then 1
       when coverage_status='complete' then 0 end as brand_presence,
  case when feature='organic' and best_organic_rank<=3 then 1
       when feature='organic' and coverage_status='complete' and
         (select count(distinct i.organic_rank) from {{ ref('silver_readable_items_v2') }} i
          where i.result_id=measured.result_id and i.organic_rank between 1 and 3)=3 then 0 end as owned_top3_presence,
  case when feature='organic' and best_organic_rank<=10 then 1
       when feature='organic' and coverage_status='complete' and
         (select count(distinct i.organic_rank) from {{ ref('silver_readable_items_v2') }} i
          where i.result_id=measured.result_id and i.organic_rank between 1 and 10)=10 then 0 end as owned_top10_presence
from measured