select
  cast(quarantine_id as varchar) as quarantine_id,
  cast(observation_id as varchar) as observation_id,
  {{ nullif_trim('engine') }} as engine,
  cast(response_id as varchar) as response_id,
  cast(source_ingestion_id as varchar) as source_ingestion_id,
  {{ nullif_trim('raw_file_hash') }} as raw_file_hash,
  cast(item_index as integer) as item_index,
  {{ nullif_trim('reason') }} as reason,
  cast(raw_item_json as varchar) as raw_item_json,
  {{ nullif_trim('parser_name') }} as parser_name,
  {{ nullif_trim('parser_version') }} as parser_version
from {{ source('silver', 'silver_serp_parsing_quarantine') }}
