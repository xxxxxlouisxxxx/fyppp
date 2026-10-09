select
  cast(raw_file_id as varchar) as raw_file_id,
  cast(request_id as varchar) as request_id,
  {{ nullif_trim('artifact_type') }} as artifact_type,
  {{ nullif_trim('raw_directory') }} as raw_directory,
  {{ nullif_trim('relative_path') }} as relative_path,
  {{ nullif_trim('sha256') }} as raw_hash,
  cast(byte_size as bigint) as byte_size,
  {{ nullif_trim('content_type') }} as content_type,
  cast(created_at as timestamp) as created_at_utc
from {{ source('bronze', 'raw_files') }}
