select
  cast(brand_domain_id as varchar) as brand_domain_id,
  cast(brand_id as varchar) as brand_id,
  {{ nullif_trim('domain') }} as domain,
  cast(recorded_at as timestamp) as recorded_at_utc
from {{ source('bronze', 'brand_domain_registry') }}