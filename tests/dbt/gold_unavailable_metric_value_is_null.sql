select metric_id
from {{ ref('gold_serp_brand_visibility') }}
where availability_status <> 'available'
  and metric_value is not null

union all

select metric_id
from {{ ref('gold_llm_brand_visibility') }}
where availability_status <> 'available'
  and metric_value is not null

union all

select metric_id
from {{ ref('gold_comparison_brand_metrics') }}
where availability_status <> 'available'
  and metric_value is not null
