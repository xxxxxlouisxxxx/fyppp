# V1 engineering increment: review, evidence and recovery

## Status — 2026-10-08

DS0 findings and fixture-first implementation plan were approved by the requesting
user. This increment implements reusable plumbing, **not full V1.0 acceptance**.
No paid collection, production data migration/backfill/publication, registry entity
approval or real-data acceptance batch was performed.

Implemented and fixture-verified:

- Completed release ID rejection before initialization/writes, with byte-hash
  regression tests; assessment, metric snapshots, optional evidence and pointer
  publication share one transaction. Failed evidence publication rolls back release.
- Approved original-field evidence snapshots: checksum + metric/observation/hash
  lineage + explicit JSON pointer + reviewer/reason/time + parser/registry versions.
  Original snippets/answer strings and safe HTTP(S) URLs are copied, never generated.
- Separate append-only SQLite review events, controlled command writer, optimistic
  sequence checks, release-scoped metric/evidence references and counter-evidence.
- Five dashboard tabs, evidence explorer, separate review history filtered to the
  selected release. Need taxonomy is explicitly unavailable, not inferred. Brand
  competition retains exploratory legacy data; formal v2 analysis is not activated.
- Explicit cold-backup file scope and hash manifest; restore to a new independent
  directory only. Tampered bundles and live overwrite fail closed.

## Review / action interface

The controlled writer is the module `geo_research.storage.reviews`, separate from
the Streamlit consumer. It is explicitly invoked; opening the dashboard never writes
review events or initializes a store. All options below can be inspected through
the module's `--help` and `append --help`.

- Global `--store`: explicitly selected separate local .sqlite/.sqlite3 store.
- `history`: optionally restrict with `--opportunity-id`; missing store returns
  empty and is not created. Existing store is opened in SQLite `mode=ro`.
- `append`: requires existing `--warehouse`, `--opportunity-id`, `--release-id`,
  `--expected-sequence`, `--status`, `--classification`, `--reviewer`, `--reason`
  and at least one `--evidence` ID. Optional repeatable `--counter-evidence` and
  `--next-action` capture contradictory evidence and the concrete next step.

New opportunities start at expected sequence 0 and status `new`. Read current
history before subsequent events; stale sequence fails rather than overwriting.
Statuses: new → in_review → needs_evidence/action_planned → experiment_running
→ closed/archived, with bounded reassessment transitions. Archived is terminal.
Action planned / experiment running requires a nonblank next action.

Evidence classifications are observation, interpretation or hypothesis. The writer
does **not** support validated-opportunity claims or registry promotion. Manual
classification changes require the recorded reviewer/reason; status never upgrades
classification automatically. Retain historical events; no UPDATE/DELETE interface.

Set `GEO_REVIEW_STORE` to an existing store for optional read-only dashboard history,
or use the dashboard's local path field. Review state is independent of analytical
snapshots. Store location, access controls and retention must be approved before
production use. SQLite triggers are application-integrity guards, not tamper-proof
storage against an administrator. Local path selection is not public-deployment safe.

## Original evidence publication

Programmatic publication accepts a tuple of `ApprovedEvidence` records via
`ReleaseRepository.complete(..., evidence=...)`. No automatic source-field discovery
or approval is performed. Fields identify actual raw bytes and an RFC6901 pointer.

Every reference must match one snapshot metric's observation and raw hash. Original
source field must be a nonempty string. Citation/result URLs require HTTP(S), a host
and no embedded user credentials. Only `experimental` quality is supported by this
increment: display approval is not an extraction benchmark approval. Human reviewers
must check source-field semantics, sensitive content and permitted exposure.

No raw files or current registries are read by the dashboard. It queries only fixed
completed-release snapshots. Historical releases without evidence remain readable;
empty evidence is disclosed. Incompatible evidence schema fails closed. Reusing a
completed release ID is rejected, including when current Gold is incomplete.

Scope limits: need mappings, complete feature contracts, citation occurrence/entity
analytics and validated v2 feature publication are not added by this display API.
Legacy metric semantics and historical data are not rewritten. No claim of extraction
precision/recall is made. Citation URL evidence is not a computed citation share.

## Backup / independent restore

The controlled module `geo_research.storage.recovery` exposes `backup` and `restore`.

`backup` requires an explicit root, a **nonexistent external destination**, repeatable
relative `--file` paths, reviewer/reason and `--writers-stopped`. Stop collection,
transformation, publication and review writers; close/checkpoint databases first.
Active database journal sidecars fail closed. The confirmation flag is an operator
attestation, not a cross-process lock; concurrent writers are not supported.

Scope must include approved raw evidence, frozen registries, completed snapshot
warehouse, build/run manifests, parser/metric code/config references and review store.
The implementation copies only operator-selected regular files; it does not infer
that the selected scope is complete or that a release was commercially validated.
Keep backups private: snapshots/reviews can contain sensitive research evidence.
Environment/secrets are not a backup configuration-reference substitute.

`restore` takes an existing bundle and a nonexistent independent destination. It
verifies manifest version, safe relative paths, byte sizes and hashes before copy,
then verifies restored bytes. Existing destination/unsafe paths/tampering are rejected.
Never restore over live warehouse as a test. Select the restored warehouse explicitly
and compare releases, original evidence and review history. The hash manifest detects
accidental corruption; it is not a signed authenticity proof against an attacker.

## Verification evidence

On configured Python **3.14.4**:

- 49 tests passed across [release tests](../tests/unit/test_releases.py),
  [review tests](../tests/unit/test_reviews.py),
  [evidence tests](../tests/unit/test_release_evidence.py),
  [recovery tests](../tests/unit/test_recovery.py) and
  [dashboard tests](../tests/unit/test_dashboard.py).
- All warehouses/review stores/raw examples used in those tests are disposable
  pytest fixtures. Streamlit AppTest verifies the five tabs and empty filter state.
- Two fixture releases plus two review histories were backed up/restored into a new
  directory and compared byte-for-byte. This is **fixture rehearsal only**, not two
  approved real-data batches.
- Focused Ruff and editor diagnostics are checked separately. Full pytest/dbt,
  supported Python 3.12, benchmark review and production restore remain pending.
- Focused strict mypy passed for the three new storage modules (evidence, reviews,
  recovery), with imported modules skipped; not a full-repository type pass.

## Remaining V1.0 acceptance gates

1. Complete portable raw integrity and response-based coverage audit.
2. Approved real brands/aliases/domains, need taxonomy and semantic comparison scope.
3. Human annotation dataset, per-feature/stratum thresholds and benchmark results.
4. Complete versioned v2 metric contracts/quality gates and formal five-page analytics.
5. Scoped deterministic execution, durable manifests, repeat/retry and budget hardening.
6. Two consecutive approved real-data batches and operator-accepted complete recovery.
7. Supported-runtime full quality suite, security/deployment/retention approval.

Refer to [the implementation plan](v1_implementation_plan_20261008.md). These missing
gates are not automatically approved by engineering tests. Do not declare V1.0 done.