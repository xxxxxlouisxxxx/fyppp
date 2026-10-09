select metric_id
from {{ ref('gold_serp_brand_visibility') }}
where availability_status = 'available'
  and numerator = 0
  and metric_value is null

union all

select metric_id
from {{ ref('gold_comparison_brand_metrics') }}
where availability_status = 'not_collected'
  and metric_value is not null
