{{ config(enabled=false) }}

select
  cast(attempt_id as varchar) as attempt_id
from {{ source('bronze', 'api_attempts') }}