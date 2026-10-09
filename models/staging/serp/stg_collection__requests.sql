{{ config(enabled=false) }}

select
  cast(request_id as varchar) as request_id
from {{ source('bronze', 'api_requests') }}