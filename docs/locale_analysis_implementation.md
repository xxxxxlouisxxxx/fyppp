# Region and language analysis: first implementation

## Scope

Use existing collected evidence without new API calls or raw modifications.
This release implements analysis dimensions and safe comparison foundations,
not the dashboard, semantic intent classification or validated business scores.

## Data contract

- Silver observation views preserve `raw_language_code` and `raw_location_code`
  from storage. Analysis language codes are trimmed, lowercased, and `_` becomes
  `-`: `zh_CN`, `zh-CN` and `ZH-cn` all become `zh-cn`. No language detection,
  translation, or mapping between `zh`, `zh-cn`, `zh-tw` and `zh-hant` is inferred.
- Analysis location codes are trimmed strings. Exact provider location identity
  is retained: country and city codes are not automatically combined. No country
  label is guessed from a code. Null/blank metadata remains unknown.
- Gold carries locale metadata, source dimensions and `collected_at`. This is
  the timezone-aware Bronze response receive timestamp, not the search engine's
  result generation time. LLM collection windows come from recorded requests.
- Presentation snapshot migration 007 adds nullable fields without rewriting
  historical releases. Old releases retain null context rather than invented
  values. New release publication requires the updated Gold schema; explicit
  snapshot column lists protect against column-order changes.
- Requested region/language do not establish that an LLM applied personalization.
  Keep that caveat visible in any dashboard built on this evidence.

## Coverage view

`silver_locale_evidence_coverage` counts distinct parsed observations by source,
query/prompt identity, locale, platform/model, device, window and collection
status, before the Gold observation-by-brand expansion. Counts are not expected
collection counts, distinct raw-file counts or statistically independent trials.
Unsupported raw engines never parsed into Silver are not included; report that
limitation rather than claiming this is an exhaustive raw inventory.
The view is an internal diagnostic: dashboards must not directly read Silver.

## Approved comparisons, version 2.0.0

Only active query-to-prompt registry mappings authorize cross-source comparison.
Different wording/languages do not establish equivalent intent. This change
does not create mappings or infer semantic equivalence from text.

Latest evidence is selected within normalized locale, explicit window and source
slice using response receive time descending, nulls last, then observation ID.
SERP slices retain provider, engine, search type and device; LLM slices retain
provider, platform and model. Different raw spellings of a normalized locale do
not create independent slices.

Pairing requires nonnull matching language, location and explicit window IDs.
Approved mappings can retain multiple engine-platform pairings within the same
context; these are separate exploratory rows, not a pooled independent sample.
LLM device is not currently available, so equal-device eligibility is not claimed.
Equal window IDs establish a recorded grouping, not a bounded timestamp distance.
Unknown receive timestamps are exposed, not fabricated.

- `matched_context`: both observations have the required matching context.
- `unmatched_context`: known context has no matching opposite-channel slice.
- `missing_context`: an observed slice lacks language/location/window metadata.
- `not_collected`: the approved mapping has no observations on either channel.

Unavailable observations retain statuses and null comparison values. They do
not imply brand absence. `comparison_brand_presence` is LLM binary presence minus
owned-organic SERP presence, with values -1, 0 or 1 only when both are available.
This is not LLM mention share minus organic slot share and is not Top10 coverage:
validated collection depth is not exposed. Underlying channel values remain
available for inspection. Legacy summary score column names are retained but now
describe binary presence only, not monetary opportunity.

## Validation and follow-up

- In-memory SQL tests render actual project macros/models and cover locale
  preservation, blank metadata, timestamp recency, multiple sources, incompatible
  windows/locales, approved mappings, null gaps and unique context-aware IDs.
- Migration/release tests verify old rows survive, metadata roundtrips, and
  outdated Gold schemas cannot silently publish context-free new releases.
- dbt tests verify Gold locale lineage, matched context and binary gap formulas.
- Full dbt validation must use an isolated warehouse because the existing
  on-run-start hook inserts sanitized Bronze fixture rows.

Next work: audited raw coverage (including unsupported engines), explicit
multilingual intent-group registry with reviewed mappings, true mention/citation
evidence extraction and product cards, then release-backed dashboard filters and
evidence cards. Commercial demand, traffic and conversion validation remain
separate from visibility analysis. No new real API calls are needed to start.