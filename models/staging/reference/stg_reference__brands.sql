select
  cast(brand_id as varchar) as brand_id,
  {{ nullif_trim('canonical_name') }} as canonical_name,
  cast(active as boolean) as active,
  cast(recorded_at as timestamp) as recorded_at_utc
from {{ source('bronze', 'brand_registry') }}