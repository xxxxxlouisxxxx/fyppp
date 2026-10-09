{{ config(enabled=false) }}

select
  cast(raw_file_id as varchar) as raw_file_id
from {{ source('bronze', 'raw_files') }}