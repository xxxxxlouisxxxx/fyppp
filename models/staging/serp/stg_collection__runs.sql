{{ config(enabled=false) }}

select
  cast(run_id as varchar) as run_id
from {{ source('bronze', 'ingestion_runs') }}