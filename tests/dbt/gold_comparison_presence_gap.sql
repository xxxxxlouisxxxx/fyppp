select metric_id
from {{ ref('gold_comparison_brand_metrics') }}
where availability_status = 'available'
  and (
    comparison_eligibility <> 'matched_context'
    or metric_value is null
    or metric_value not in (-1, 0, 1)
    or metric_value <> (llm_metric_value > 0)::int - (serp_numerator > 0)::int
  )