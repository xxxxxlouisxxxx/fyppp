# V1.0 implementation plan — DS0 proposal, 2026-10-08

**Status: DS0 findings and implementation plan approved by the requesting user
in this conversation on 2026-10-08.** Fixture-first engineering may proceed;
production data migration/backfill/publication and paid calls remain unapproved.
Prerequisite: [DS0 findings](ds0_audit_20261008.md) and
[extraction benchmark design](ds0_extraction_benchmark_20261008.md) reviewed.
The existing [roadmap](implementation_roadmap.md) is retained as historical context;
this plan reuses the actual code instead of restarting its earlier phases.

## Approval record (human completion required)

| Field | Value |
|---|---|
| Plan revision | DS0-V1-proposal-20261008-1 |
| DS0 decision | Findings and implementation plan approved by requesting user |
| Reviewer / approved date / reason | Requesting user / 2026-10-08 / explicit chat approval: 批准 DS0 findings 同實施計劃 |
| Approved scope / excluded features | unresolved |
| Fixture-only engineering permission | approved; production-data acceptance remains separate |
| Production migration / backfill permission | not granted |
| Paid collection permission / budget | not granted |
| Feature thresholds / benchmark version | unresolved |
| Review-store deployment / retention | unresolved |

### User scope clarification — 2026-10-08

The requesting user approved all existing same-index query↔prompt pairs (001–068).
Research is keyword/prompt-result-driven, with **no required preselected brand**.
See [mapping and brand scope decision](instrument_brand_scope_20261008.md).
Candidate discovery/review still precedes formal entity KPI approval; an owned-brand
selection is optional. This resolves pairing approval, not budgets or extraction gates.

Approval of engineering is not approval of registry entities, metrics, paid runs,
production backfill or commercial opportunities. Keep these gates separate.

## B0 — Close audit blockers and freeze contracts

1. Establish Python 3.12 test environment, fixture-only no-network verification and
   production-path denylist. Do not reinterpret a 3.14 result as supported-runtime pass.
2. Complete read-only portable raw checksum/size/orphan audit and response-based
   active-assignment coverage. Resolve paths explicitly; no automatic index repair.
3. Freeze approved source/assignment/need/brand scope and mapping registry versions,
   reviewer, reason, effective dates and approval timestamps. Candidate dictionaries
   remain distinct; no auto-promotion or default real brand choices.
4. Approve canonical availability translation: available, available-empty,
   not-collected, pending, failed, unsupported, quarantined, missing-context.
   Preserve legacy values/version in historical releases; translate only by explicit
   versioned contract. Feature absence is not collection status.
5. Define assignment, submission, retrieval, provider task, observation, intentional
   repeat and retry identities. Retry keeps observation/repeat identity; intentional
   repeat is new identity even with identical content. Study collection stays deferred
   unless separately approved; no automatic 40× refresh.

**Exit:** named approvals, integrity report, scoped coverage with unresolved reasons,
contract fixtures and proposed migration compatibility plan. Do not publish yet.

## B1 / V0.1 — Foundation hardening

Reuse [repositories](../src/geo_research/storage/repositories.py),
[identity](../src/geo_research/collection/identity.py),
[manifests](../src/geo_research/collection/manifest.py),
[raw-store tests](../tests/unit/test_raw_store.py),
[transform orchestration](../scripts/transform_all_raw.py).

Priority changes after approval:

- Freeze assignment/registry snapshots per batch; persist approved scope, stage
  prerequisites, attempt history, parser version, errors and resumable checkpoints.
- Apply consistent approved-brand/effective-date eligibility to all new formal
  paths; legacy staged active rows must not imply ownership approval.
- Add retry/repeat observation keys and unique constraints; repeated successful
  resume does not increase KPIs; preserve identical-content intentional replicates.
- Reconcile accepted tasks before any new paid submission. Source selector casing
  is already fixed; add/retain regression coverage instead of redoing the old fix.
- Inspect actual budget call paths; enforce finite nonnegative caps, shared daily
  ledger and true engine/platform totals. Unknown estimates fail closed.
- Unknown payloads retained/quarantined; only affected feature denominators blocked.

**Tests:** unknown/empty/error/pending fixtures; submit/retrieve lineage; no double
count on retries/resume; identical-content repeats preserved; candidate exclusion;
recovery after failed transaction; bounded budget and ambiguous POST no resend.
All warehouses disposable. **Exit:** approved foundation contracts and passing
tests with frozen fixtures, no raw/old-release mutation.

## B2 / V0.2 — Versioned validated analytics

Reuse [v2 enrichment](../src/geo_research/transforms/feature_evidence.py),
[feature Gold](../models/gold/gold_feature_brand_visibility_v2.sql),
[comparison contexts](../models/gold/gold_comparison_brand_metrics.sql).

For each metric persist name/version, meaning/nonmeaning, grain, sample unit,
eligible population, numerator/denominator or explicit not-applicable, availability,
provider/locale/window, registry/parser version, lineage, quality and limitations.

| Metric family | Proposed grain / denominator rule (approval required) |
|---|---|
| Answer brand presence rate | Distinct approved observation-brand; eligible complete answer observations. Partial positive evidence separately reported, not negative-capable denominator |
| Answer mention occurrence count | Distinct visible-text item/field/span per brand; count metric, not forced `numerator <= denominator` |
| Organic presence rate | Eligible complete organic observations; presence distinct from item-share |
| Organic item share | Distinct eligible organic item IDs; resolve multi-brand/domain ambiguity explicitly; never double-count aliases |
| Citation presence / unique citation share | Unique conservative URL identities within declared result/observation unit; denominator all eligible citation identities, attribution policy versioned |
| Citation occurrence count | Every explicit occurrence path; separate from unique entity and owned-domain hit count |
| Cross-channel mismatch | Approved mapping + equal known locale/window + approved source pairing; pairs not independent samples; channel rates never use expanded pairs |
| Concentration / HHI | Declared observed item/entity population including explicit unknown/unattributed handling; no approved-only renormalized market claim |
| Repeat variability | Genuine recorded replicate IDs and disclosed dependence/cache; descriptive unless assumptions approved |

Run approved human benchmark before validated labels/publication. Unsupported or
below-threshold strata stay experimental/unavailable, not zero. Align fixtures,
SQL, release validator and dashboard `matched_context` vocabulary. Keep historical
metric versions intact; do not change legacy labels in place.

**Exit:** approved contracts, benchmark report + feature-specific approvals, fixture
SQL/dbt tests, metric-grain/denominator tests, unavailable-null tests and coverage
gates. New metric population cannot be inferred from old current registries.

## B3 — Immutable release and evidence snapshot contract

Reuse [release repository](../src/geo_research/storage/releases.py),
[migrations](../src/geo_research/storage/migrations.py),
[read-only consumer](../src/geo_research/dashboard/data.py).

1. Reject reuse of completed release IDs before metadata or snapshot mutation.
   Idempotent resume must verify the same frozen manifest, not replace snapshots.
2. Perform assessment/publication from one consistent source transaction or frozen
   build artifact. Current pointer changes only after all required gates succeed.
3. Persist source scope, run manifest, frozen registry/parser/metric versions,
   build artifacts/checksums, quality decisions, snapshot identities, status and
   recovery reference. Rollback only changes pointer to existing completed release.
4. Add explicitly approved release-scoped evidence snapshots: original snippet/text
   representation and extraction method, URL/citation entity/occurrence, observation,
   task/result/item/path/hash lineage, need mappings, source context and versions.
   Redact sensitive fields by approved policy; no full raw subtree in public view.
5. Evidence and metrics must match release scope and referential integrity. Dashboard
   cannot query live raw/Silver or guess historical mapping from current CSVs.

**Tests:** republish completed ID leaves bytes/rows/current unchanged; draft/failed
release cannot be current; gate failure leaves previous release usable; stale build,
benchmark rejection, missing lineage or mixed release rejected; SQL parameters;
historical snapshot reproducibility; consistent evidence drill-down.

## B4 / V1.0 — Five-page dashboard and controlled review

Reuse [existing app](../src/geo_research/dashboard/app.py) and
[dashboard tests](../tests/unit/test_dashboard.py); preserve fixed allowlists,
read-only connections, materialized transaction and one selected release.

1. **Overview:** scoped coverage, statuses, distinct sample counts, approved metrics,
   quality/freshness/unknowns and release context.
2. **Need × Market Map:** approved need mappings only, language/source/window
   slices, numerator/denominator and coverage; no controlled-country-effect claim.
3. **Brand Competition:** approved brand presence vs item/citation share; HHI with
   population/unknown labels; unapproved candidates excluded.
4. **Evidence & Citation Explorer:** original approved release snippets, URLs,
   occurrences/entities, quality and full lineage; no generated missing citations.
5. **Opportunity Queue:** evidence-linked hypotheses, counter-evidence, coverage
   limitations, review history and next actions; no automatic commercial approval.

Proposed review persistence: separate local append-only SQLite event store with a
controlled CLI/service writer, not writes through the analytical dashboard. Owner
must approve it. Dashboard remains read-only for both stores; action entry uses
that separately authorized interface. Each event has opportunity/release/evidence
IDs, reviewer, UTC timestamp, reason, prior/new workflow state and next action.
Validate references against frozen completed release and use concurrency control.

Workflow: New → In review → Needs evidence → Action planned → Experiment running
→ Closed / Archived. Evidence class is independent: Observation / Interpretation /
Hypothesis / Validated opportunity. A workflow transition never upgrades evidence;
commercial validation requires explicit reviewed validation evidence.

**Tests:** five pages same release; filter unknown vs zero; empty evidence states;
candidate exclusion; independent channels vs paired counts; allowed workflow moves,
required reviewer/reason/evidence, append-only audit trail; controlled action writer
cannot modify snapshots; readers never initialize DBs or invoke collection.

## B5 — Deterministic operations and acceptance

Transformation runner executes only approved deterministic stages, checks versioned
prerequisites, records manifests/errors and suggests bounded reruns. It cannot
change metric semantics, approve registries, bypass gates or retry paid work forever.

Create hash-verified backup manifest covering immutable raw, frozen registries,
completed snapshots, batch/build artifacts, code/config references and review events.
Restore into a distinct empty destination; reject live path/overwrite. Verify hashes,
release selection, evidence links and review history against the backup manifest.

Execute **two consecutive approved batches** through audit → scoped transform →
metric/build checks → approved release → all five pages → action event, with original
evidence comparisons and independent backup/restore. Fixture rehearsal is labelled
fixture-only and does not substitute for approved real-data acceptance.

## V1.0 acceptance checklist (all pending)

- [ ] DS0 report, contracts, scope and implementation approval recorded.
- [ ] Scoped current usable coverage and complete raw integrity audit accepted.
- [ ] Human extraction benchmark passes approved per-feature/stratum gates.
- [ ] Formal metric grains/versions/denominators/availability/lineage accepted.
- [ ] Candidates excluded; missing/empty/failed/unsupported/confirmed absence separate.
- [ ] Immutable completed releases; approved evidence snapshots only.
- [ ] All five pages hold selected release; conservative comparisons/claims.
- [ ] Persistent review/action interface and audit trail accepted.
- [ ] Two consecutive approved batches with signed evidence records.
- [ ] Independent backup/restore verified, including review state.
- [ ] Python 3.12 pytest/Ruff/mypy + isolated dbt and UI checks recorded.
- [ ] Runbooks, costs, security, deployment limits and unresolved decisions disclosed.

V1.1–V2.0 external demand/commerce/trade, scoring and paid 40-repeat execution are
not part of this V1 implementation authorization. Original HKTDC formal acceptance
remains separate and blocked until its source is supplied; never invent ten criteria.