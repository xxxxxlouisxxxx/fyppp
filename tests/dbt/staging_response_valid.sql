select response_id
from {{ ref('stg_dataforseo__responses') }}
where response_valid is null