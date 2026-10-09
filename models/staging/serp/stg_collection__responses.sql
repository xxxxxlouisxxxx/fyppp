{{ config(enabled=false) }}

select
  cast(response_id as varchar) as response_id
from {{ source('bronze', 'api_responses') }}