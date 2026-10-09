select metric_id
from {{ ref('gold_serp_brand_visibility') }}
where availability_status = 'available'
  and denominator <= 0
