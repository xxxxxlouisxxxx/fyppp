# DS0 extraction benchmark specification — proposed, not approved

Purpose: validate measurement before any new formal V1 metric release. Existing
[v2 fixtures](../tests/unit/test_feature_evidence.py) cover plumbing, not a reviewed
ground-truth benchmark. This document neither labels raw evidence nor approves
quality thresholds. See [audit](ds0_audit_20261008.md).

## Approval contract

Record benchmark ID/version, approved feature/stratum scope, reviewer, date, reason,
sample counts, risk rationale, precision/recall gates, minimum support, treatment of
unsupported strata and expiry/revalidation triggers. **All values unresolved.**
No common percentage or sample size is silently selected by the coding agent.

Feature gates: answer-only presence, answer occurrence spans, organic eligibility /
ownership, citation occurrence extraction, canonical unique citation identity,
domain attribution and approved query↔prompt semantic equivalence. Category/need
classification receives its own reviewed taxonomy gate; no terms inferred as approved.

## Frozen sampling frame

- Approved assignment scope, actual collection window, immutable raw hash and
  registry/parser versions; no Cartesian-product denominator.
- Stratify source/platform, language, provider location, instrument/need, item kind,
  available/empty/unsupported/quarantined status and approved/candidate identity.
- Include positive/negative, ambiguous aliases, Latin/CJK boundaries and Unicode
  casefold expansion; only source metadata mentions vs true answer mentions.
- Include repeated URLs/fragments/default ports/query strings, invalid URLs,
  host spoofing/user-info URLs, null sources vs explicit empty list, tables,
  result markdown fallback, unknown nested/top-level items and multiple results.
- Include owned domain vs reseller/publisher title mention; paid vs organic;
  missing organic ranks vs proved Top3/Top10 absence.
- Cluster related samples by observation/task and instrument; prevent overlapping
  blocks, duplicate content or same task from masquerading as independent support.
- Separate development examples and untouched evaluation set. Document exclusions
  and selection bias. Rare strata are reported, not pooled away to pass gates.

## Annotation schema (proposed)

One annotation links `benchmark_id`, `sample_id`, immutable raw hash, observation/
task/result/item/path, original field representation, parser/registry version,
source/locale/window, feature, identity status, human label, occurrence/span or URL
identity, evaluability, unsupported reason, annotator, UTC timestamp and rationale.

Labels distinguish present, confirmed absent, not evaluable, unsupported and
ambiguous. Missing raw or incomplete relevant feature cannot be confirmed absent.
Candidate mentions can be literal true positives for candidate extraction but do
not become approved-brand KPI labels. Brand-domain ownership requires independent
reviewed source, not a source URL containing the alias.

Use separate annotation storage; never modify raw. Show minimum necessary evidence
to authorized reviewers; reports include reference IDs and aggregate errors only.
Original text and selected visible representation must be distinguishable; URL-token
removal or table flattening is a method, not the raw original.

Double-review ambiguous/high-risk examples; record adjudication and disagreements.
Approve the reviewer/adjudication protocol and sampling numbers before execution.

## Evaluation

For evaluable reviewed examples, report TP/FP/FN, precision `TP/(TP+FP)` and recall
`TP/(TP+FN)` by feature and stratum. Zero prediction/positive support yields unknown
where denominator is zero, not artificial 100%. Always publish support, exclusions,
unsupported rate and error categories. Precision/recall is not sample coverage.

- Presence: observation-brand binary unit on complete relevant feature.
- Mentions: original span matching with agreed alias overlap policy; alias entries
  are not occurrence counts. Record boundary false positives/false negatives.
- Citation occurrence: explicit path/URL occurrence; unique entity evaluated
  separately under conservative approved normalization version.
- Domain attribution: reviewed brand-domain relationship, not substring URL hit.
- Need/mapping: reviewer semantic-equivalence judgement in scoped locale/window,
  not similarity or equal text; compare instruments separately from extraction.

Mention counts need not be bounded by answer-block count. Apply numerator ≤
denominator only to defined proportions, not arbitrary counts.

## Publication gate / revalidation

Persist dataset/annotation hashes, methodology/version, approved thresholds,
per-feature/stratum results, reviewer and scope-limited approval with release lineage.
Unapproved, below-threshold, insufficient-support or unsupported features remain
experimental/unavailable. No threshold fallback or silent pooling/reweighting.
Parser, registry, schema, taxonomy or normalization changes trigger explicit review
and new release/backfill approval; old release labels/snapshots remain immutable.

## Deliverables and current state

- Frozen sample manifest: pending scope/sample approval and complete integrity audit.
- Reviewed annotation/adjudication dataset: not created in DS0.
- Per-feature precision/recall/support/error report: not executed.
- Gate decisions tied to release scope/version: not approved.
- Fixtures converted from reviewed examples: future engineering after approval.

Until these artifacts exist, implemented feature extraction is not described as
validated answer-only extraction or a validated commercial opportunity.