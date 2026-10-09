select current_slot.release_id
from {{ source('presentation', 'release_current') }} as current_slot
left join {{ source('presentation', 'releases') }} as releases
  on releases.release_id = current_slot.release_id
where current_slot.slot = 'current'
  and (
    releases.release_id is null
    or releases.status <> 'completed'
  )
