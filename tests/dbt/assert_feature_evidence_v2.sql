select feature_id as failure_id from {{ ref('silver_feature_coverage_v2') }}
where observed_count < 0 or exhaustive_count < 0
  or (coverage_status != 'complete' and exhaustive_count is not null)
  or (coverage_status = 'complete' and exhaustive_count is distinct from observed_count)
union all
select item_id from {{ ref('silver_readable_items_v2') }}
where (item_kind != 'organic' and organic_rank is not null)
  or (item_kind = 'organic' and organic_rank is distinct from rank_group)
  or page_position is distinct from rank_absolute
union all
select result_id from {{ ref('silver_evidence_results_v2') }}
where parse_success_rate not between 0 and 1
  or parsed_top_level_item_count > top_level_item_count