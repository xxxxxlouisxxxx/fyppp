# Silver response composition and atomic evidence (MVP v1)

Additive v2 readable views, per-feature coverage, citation entities, candidate review
and versioned Gold are documented in [feature_evidence_v2.md](feature_evidence_v2.md).
The global completeness gates below describe preserved **v1**, not v2 metrics.

## Integration and safety

The offline bulk transform automatically enriches **new** warehouses after actual
Bronze registry seeding and before table exports. Both unrestricted and date-scoped
runs use the same integration. No collection, raw mutation, database overwrite or
release publication is performed. Migration 008 adds four tables; dbt wraps them
as views. Existing databases are not backfilled merely by running dbt.

The ordinary `transform_bronze_to_silver` job still performs parsing only. This
feature's persisted integration is the isolated offline bulk job. Integrity-invalid,
unsupported-provider and quarantined-before-observation files remain in its audit
reports; they are not invented as successfully collected observations.

## Grains and lineage

- `silver_response_summaries`: one existing SERP/LLM observation, never pooled by
  query, locale, platform or timestamp. Request/response/hash, query/prompt text,
  provider, engine/platform/model, locale, collection timestamp, task and status
  accompany the summary. SERP's supported multiple results are inspected with
  distinct paths within that existing observation grain. Multiple tasks and multiple
  LLM results are unsupported, not silently truncated.
- `silver_response_items`: one top-level item or supported nested product, image,
  related-search string, citation/source occurrence or inline answer link. Stable
  IDs derive from observation, JSON path and enrichment version. Child rows carry
  parent IDs; all rows retain their raw subtree. Result-level sources have no block
  parent. Inline links retain their extracted URL and exact originating field/path.
- `silver_item_brand_evidence`: many-to-many item/brand/field/span evidence with
  method, method version and content-hashed actual Bronze registry version.
- `silver_item_category_evidence`: many-to-many item/category/reviewed-rule evidence,
  including matched field/term, rule ID/version and taxonomy version.

Join item `observation_id` to summaries, and bridge `item_id` to items. Join summary
`request_id` to Bronze requests for authoritative query/prompt/target/window context;
`query_id` is the preserved Bronze query ID (prompt ID for LLM), not an inferred topic.
Join `response_id` to Bronze responses and hash/path to raw evidence for drilldown.
Do not join SERP and LLM by query text to infer approved comparison mappings.

## Counts and completeness

`provider_reported_item_count` is separate from actual `top_level_item_count`.
`organic_count` counts organic top-level records. `product_card_count` counts nested
shopping/LLM product cards, not product modules or mentions. `answer_block_count`
counts LLM text/table blocks. `image_count` includes image-module children and nested
images. `citation_count` counts source/link **occurrences**, not unique URLs: result,
block and inline occurrences remain distinguishable by path. `atomic_item_count`
includes top-level containers and children; it is not a recommendations count.
`result_types` is the distinct raw top-level format set, not business categories.

Semantic totals are null unless the whole applicable response was inspected.
Pending/error/missing/unsupported/quarantined observations never become semantic
zeros. Unsupported or unavailable nested content produces `partial`, preserved raw
evidence and `issues_json`; structural top-level counts remain if independently known.
Partial arrays list observed positive evidence only, not exhaustive absence. Atomic
rows have their own coverage status. Fully inspected empty applicable content can
produce zero. With no eligible approved brands, brand totals stay null and
`brand_coverage_status` is `no_approved_registry` (not "no brands exist").

## Identity policy

Actual Bronze registry rows only: active brands with explicit `owned` or `competitor`
ownership, valid effective dates, no TO_BE_VERIFIED, placeholder/example/sanitized
identities. Registered aliases/domains must belong to those brands and be effective
at collection date. Activity alone never verifies ownership. No inferred identity
or domain is added or approved.

English/Latin matching uses casefold and Unicode word boundaries. CJK matching uses
substring spans with longest-overlap suppression. Same longest ambiguous alias may
retain multiple registered identities, without choosing or approving one. Original
text offsets are retained across casefold expansion; Markdown answer matches refer
to visible link-label text, not URL tokens. Text representations are selected once,
so result Markdown is not counted again alongside blocks.

Evidence channels: owned SERP hostname, SERP title/snippet, answer text, product
title/description/explicit brand, and registered owned citation hostname. Source
snippets are never answer mentions. Product merchant/source/domain is never used as
the product manufacturer. Hosts use parsed exact or dot-suffix registry matching;
spoof suffixes and URL credentials do not match. Citation URLs do not prove product
brand or ownership of third-party publishers. `answer_brand_ids` and `cited_brand_ids`
are separate; overall arrays/count deduplicate registered identities.

Legacy Gold matching strips additive `raw_item`, `result_sources` and `json_path`
fields before its existing item-string matcher. Gold semantics and dashboard outputs
are otherwise unchanged; the new evidence does not redefine legacy visibility.

## Explicit categories

The category CSV intentionally contains headers only: **no pretend reviewed taxonomy**.
Default summary is `business_categories = ['unknown']`. To populate rules, a reviewer
must supply `rule_id,category_id,category_name,term,matched_field,item_kind,`
`taxonomy_version,rule_version,review_status,active`. Only `approved,true` rows apply.
Fields are limited to content title/description/answer text/explicit brand or explicit
raw product `category`/`product_category`; merchant/source metadata is disallowed.
Use a concrete item kind or `*`. Terms use the same boundary/CJK matcher. Multiple
rules/categories may match one item; totals need not sum to item or brand counts.
Raw category mappings have method `reviewed_raw_category_map`; textual assignments
have `reviewed_explicit_term`. Neither is described as a provider raw classification.

## Validation and limits

Tests cover actual local Baidu (11 top-level, 7 organic, 20 product cards, 9 images,
2 related modules), actual ChatGPT products/table/sources, source-only mentions,
merchant separation, aliases, spoof hosts, multilabel rules, registry approval,
null/partial coverage, transaction rollback and new isolated bulk integration.
Local raw tests explicitly skip if undistributed raw is absent. Unknown nested shapes
remain partial rather than receiving guessed schemas. No sentiment, recommendation,
sales, semantic taxonomy inference, citation URL canonicalization or Gold redesign.

Validated on configured Python 3.14.4; the project declares Python 3.12. Supported
3.12 verification remains outstanding. Production raw-folder-date 2026-09-28
verification completed on 2026-10-02: 3,427 responses/summaries, unchanged raw
hashes, full dbt build (33 views, 364 tests, one hook; no failures), and 68 finalized
Parquet exports with verified row counts. Coverage is 679 complete, 1,730 partial,
893 pending and 125 provider errors. No approved brands or comparisons exist;
Gold stays empty and no release was published. Details are in
[production verification](../data/exports/raw_date_20260928_20261002T102632_663523Z/production_verification.md).