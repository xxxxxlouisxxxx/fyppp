# Readable feature evidence v2: finite offline MVP

Migration 009 is additive. Migration 008 evidence, legacy ranks/Gold and completed
dashboard releases are not reinterpreted. New date bulk runs normalize v1 and v2
inside the same per-observation transaction after actual registry seeding. No APIs,
publication, raw edits, or previous warehouse/batch overwrites are performed.

## Readable relations

- `silver_evidence_results_v2`: one task/result context (or explicit unavailable
  observation sentinel). Request/response/hash, task/result indices/path, raw query
  text, provider/platform, normalized locale, device/OS/depth, model, collection
  timestamp and **separate raw provider result datetime**. No inferred query IDs
  or shared windows. Provider datetime remains a string to avoid guessing timezone.
- `silver_serp_results_v2`: exactly one row per top-level SERP raw item. Title,
  description, URL/domain, type, `rank_group`, `rank_absolute`, `organic_rank`
  (organic group only), `page_position` (absolute), raw subtree and context.
- `silver_readable_items_v2`: generic top-level and nested readable evidence,
  preserving parent/path and raw JSON. Unknown nested containers are separate
  `retained_nested` rows, not guessed recommendations.
- `silver_answer_blocks_v2`, `silver_products_v2`: selected visible answer text
  and product cards, not source snippets or merchant/manufacturer guesses.
- `silver_citations_v2`: conservative unique URL entities **within a result**.
  Host/scheme case, default port and fragment normalization only; path/query,
  www and HTTP/HTTPS distinctions remain. No guessed redirects/tracking removal.
- `silver_citation_occurrences_v2`: every block/result/inline occurrence with raw
  URL, parent/item/path; invalid URLs remain here with null entity, partial coverage.
- `silver_feature_matches_v2`: explicit reviewed brand/category evidence and
  separately labelled candidates. Categories are multilabel; unknown remains
  `['unknown']` in readable items without approved matches.

## Counts, status and text contracts

Organic, paid, answer_text, product and citation have independent observed counts,
coverage/issues and exhaustive counts. Observed counts are distinct atomic IDs
(citation = unique valid URL entities); exhaustive counts exist only for complete
channels. Pending/error/missing/unsupported metrics remain null. Partial positive
evidence is usable, but is not proof of absence. Unsupported paid children do not
null fully inspectable organic counts. Paid sitelinks remain child rows; paid
hostname matches are `paid_domain`, never `owned_organic`.

`parse_success_rate` uses unique successfully readable top-level item IDs / actual
top-level raw items, never quarantine events. Empty denominator is null. This new
definition does not silently replace the legacy KPI or legacy rank interpretation.

Answer fields prefer original_text, markdown, then text once. Rectangular lists of
scalar table cells have a text fallback; unsupported table shapes stay raw/partial.
Result markdown is used only when no item text was extracted, not counted again
alongside blocks. A result-only fallback does not invent missing product/citation
coverage. Link labels are answer text; source snippets and URL tokens are not.
Missing/null sources are not confirmed empty; explicit lists retain known evidence.
Unknown LLM top-level types keep potentially affected LLM channels partial.

## Review workflow (manual gate)

1. Add explicit dictionary rows to `config/registries/brand_candidates.csv`, status
   `candidate`. HOKA is the only supplied sample dictionary entry, from the user's
   literal Bing title example. No domain ownership or approved identity is implied.
2. Optional proposed multilabel rules go in `category_candidates.csv`, separate
   from `category_rules.csv`; `candidate,true` rows generate review evidence only.
3. Each offline bulk export writes `candidate_review.csv` with raw path/content,
   locale/platform, reviewer/decision/ownership-evidence/approved-ID blanks.
4. Review identities, aliases, effective dates and independent ownership evidence.
   Manually update existing formal brands/aliases/domains CSVs and approved category
   rules only after approval; there is no automatic promotion/import of decisions.
5. Repeat a new date bulk build plus dbt with fixture bootstrap false. Formal Gold
   ignores candidates. With no reviewed brands Gold is empty, not zero exposure.

`gold_feature_brand_visibility_v2` version 2.0.0 uses distinct answer occurrence
spans, unique owned citations and channel-specific owned/product slots. Positive
presence may be observed on partial evidence; exhaustive zero requires completeness.
Organic Top3/Top10 negatives require actual distinct ranks covering 1..3/1..10,
not provider depth or total module count. Eight organic rows cannot prove a
negative Top10. Legacy dashboard models are unchanged.

## Remaining limits

- Ordinary `transform_bronze_to_silver` still uses its existing parsing/status/
  engine contract. Enrichment is integrated into both ordinary **bulk** and date
  bulk orchestration, not the shared collector job; merging Baidu/status adapters
  into that job is deferred to avoid changing live behavior in this offline task.
- No semantic taxonomy inference, recommendation/sentiment, traffic/ROI, inferred
  query/prompt/window matching, new comparison panels or dashboard publication.
- Result markdown versus blocks is representation selection, not a guaranteed
  semantic equivalence proof. Unsupported tables/children stay inspectable raw.
- Reviewed registry/categories remain manual gates. Candidate matches are literal
  content evidence, not approved brands or ownership findings.
- Tests run on configured Python 3.14.4; declared supported Python 3.12 remains
  unverified. Production verification is recorded in the new export report.