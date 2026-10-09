select metric_id
from {{ ref('gold_serp_brand_visibility') }}
where numerator > denominator
