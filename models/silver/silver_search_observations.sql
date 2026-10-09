select
  cast(observation_id as varchar) as observation_id,
  cast(query_id as varchar) as query_id,
  {{ nullif_trim('provider') }} as provider,
  {{ nullif_trim('search_engine') }} as search_engine,
  {{ nullif_trim('search_type') }} as search_type,
  {{ nullif_trim('location_code') }} as location_code,
  {{ normalize_language_code('language_code') }} as language_code,
  cast(language_code as varchar) as raw_language_code,
  cast(location_code as varchar) as raw_location_code,
  {{ nullif_trim('device') }} as device,
  {{ nullif_trim('collection_window') }} as collection_window,
  cast(response_id as varchar) as response_id,
  cast(source_ingestion_id as varchar) as source_ingestion_id,
  {{ nullif_trim('raw_file_hash') }} as raw_file_hash,
  cast(has_results as boolean) as has_results,
  {{ nullif_trim('outcome_status') }} as outcome_status
from {{ source('silver', 'silver_search_observations') }}
