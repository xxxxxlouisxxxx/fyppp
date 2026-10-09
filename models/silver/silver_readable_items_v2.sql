select i.*, r.* exclude (observation_id, result_id, json_path, enrichment_version),
	coalesce((select list(distinct m.identity_name) from {{ source('silver', 'evidence_matches_v2') }} m
		where m.item_id=i.item_id and m.identity_type='brand_candidate' and m.review_status='candidate'), []) as candidate_brand_names,
	coalesce((select list(distinct m.identity_id) from {{ source('silver', 'evidence_matches_v2') }} m
		where m.item_id=i.item_id and m.identity_type='category' and m.review_status='approved'), ['unknown']) as reviewed_category_ids,
	coalesce((select list(distinct m.identity_name) from {{ source('silver', 'evidence_matches_v2') }} m
		where m.item_id=i.item_id and m.identity_type='brand' and m.review_status='approved'), []) as approved_brand_names
from {{ source('silver', 'evidence_items_v2') }} i
join {{ ref('silver_evidence_results_v2') }} r using (result_id)