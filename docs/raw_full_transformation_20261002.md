# Full offline raw transformation — 2026-10-02

## Outputs

- Warehouse: `data/warehouse/raw_full_20261002T083720_354525Z.duckdb`
- Reports/Parquet/dbt artifacts: `data/exports/raw_full_20261002T083720_354525Z`
- Reusable script: `scripts/transform_all_raw.py`

All 20,209 JSON files under raw SERP/LLM were inventoried, checksum checked and
assigned a disposition. Request/metadata artifacts were retained as provenance,
not interpreted as result records. 6,736 response files were reconstructed into
Bronze/Silver in a new warehouse. Raw checksums were unchanged; no API was called
and no existing warehouse was modified. One invalid auxiliary JSON is documented
in the manifest; all canonical response triples passed integrity verification.

## Results

| Measure | Count |
|---|---:|
| SERP observations | 6,053 |
| LLM observations | 683 |
| SERP items | 23,151 |
| Organic rows | 18,209 |
| Available responses | 2,411 |
| Pending responses | 2,546 |
| Provider-error responses | 1,779 |
| Item-level quarantine events | 4,917 |

Available is a collection outcome, not proof of a valid brand metric. Pending and
provider errors remain explicit. Item warnings are not failed response counts.
Google/Bing/Yahoo use existing parser contracts. Baidu uses the offline script's
tested generic item adapter; this does not extend the shared collector dispatch.
Live/direct LLM envelopes are normalized in memory, without overwriting raw.

## Gold and dashboard limitations

Full dbt build passed: 29 models and 343 data tests. Sanitized fixture insertion
was disabled using `bootstrap_sanitized_fixture: false`. Models and exports exist,
but brand Gold tables have zero rows because configured brands are unverified
placeholders. No approved comparisons were available. No completed release was
published and the dashboard was not switched to this ineligible warehouse.

Existing databases matched request IDs and hashes, but supplied no authoritative
query/target/shared-window metadata for these artifacts. Unknown mappings stay
null in Bronze. Non-null legacy SERP keys use labelled raw-request identities;
windows are request-isolated and cannot authorize cross-channel comparison.
CSV instruments are preserved but not guessed from similar text or numeric IDs.

To make brand KPIs meaningful, provide reviewed brand names/aliases/owned domains,
review query/prompt identity assignments and explicitly approve comparable pairs
and window grouping. Do not reinterpret empty Gold as no brand exposure.

## Inspect data

Open the new DuckDB file with a read-only client. Main relations:

- `silver.silver_search_observations`
- `silver.silver_llm_observations`
- `analytics.silver_locale_evidence_coverage`
- `meta.raw_full_request_statuses`
- `analytics.gold_serp_brand_visibility` (currently empty)
- `analytics.gold_llm_brand_visibility` (currently empty)

Manifest and request-status JSON/CSV files provide per-file outcomes; summary.json
contains reconciliation, provenance, row counts and publication blockers.