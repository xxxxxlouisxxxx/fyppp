select
  cast(brand_alias_id as varchar) as brand_alias_id,
  cast(brand_id as varchar) as brand_id,
  {{ nullif_trim('alias_text') }} as alias_text,
  cast(recorded_at as timestamp) as recorded_at_utc
from {{ source('bronze', 'brand_alias_registry') }}