select metric_id
from {{ ref('presentation_serp_brand_visibility') }}
where availability_status <> 'available'
  and metric_value is not null

union all

select metric_id
from {{ ref('presentation_llm_brand_visibility') }}
where availability_status <> 'available'
  and metric_value is not null

union all

select metric_id
from {{ ref('presentation_comparison_brand_metrics') }}
where availability_status <> 'available'
  and metric_value is not null
