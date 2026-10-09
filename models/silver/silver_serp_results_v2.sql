-- One row per actual top-level SERP item, never nested ad/product/source children.
select * from {{ ref('silver_readable_items_v2') }}
where source_category = 'serp' and is_top_level