select observation_id
from {{ ref('silver_response_summaries') }}
where
  (evidence_coverage_status <> 'complete' and (
    organic_count is not null or product_card_count is not null
    or answer_block_count is not null or distinct_brand_count is not null
    or image_count is not null or citation_count is not null
    or atomic_item_count is not null
  ))
  or (brand_coverage_status = 'no_approved_registry' and distinct_brand_count is not null)
  or (organic_count < 0 or product_card_count < 0 or answer_block_count < 0
      or image_count < 0 or citation_count < 0 or distinct_brand_count < 0)