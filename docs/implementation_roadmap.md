# Implementation Roadmap

## Proposed Repository Tree (Later Phases)

```text
.
├── docs/
├── src/geo_research/
│   ├── adapters/
│   ├── collectors/
│   ├── contracts/
│   ├── parsers/
│   ├── registries/
│   └── releases/
├── scripts/
├── tests/
│   ├── fixtures/
│   └── unit/
├── dbt_project/
│   ├── models/
│   ├── macros/
│   └── tests/
├── streamlit_app/
├── config/
├── registries/
└── .github/workflows/
```

## Phase 1: Repository Foundation

- **Objective:** Create Python 3.12/uv project metadata, src layout, quality tooling, and Git safeguards.
- **Prerequisites:** Phase 0 acceptance.
- **Allowed work:** `pyproject.toml`, ignores, pre-commit, CI skeleton, package markers, test scaffolding.
- **Prohibited work:** API calls, database creation, dbt models, Streamlit pages.
- **Files expected:** Project metadata, `src/`, `tests/`, `.github/`, configuration samples.
- **Test strategy:** Import, Ruff, mypy, pytest, and secret/ignore checks.
- **Definition of done:** Tooling runs locally and CI makes no networked provider calls.
- **Rollback point:** Revert the Phase 1 commit.

## Phase 2: Registry Contracts

- **Objective:** Define validated CSV schemas for all registries.
- **Prerequisites:** Phase 1.
- **Allowed work:** Pydantic models, CSV templates, validation CLI, tests.
- **Prohibited work:** Collection or analytics implementation.
- **Files expected:** Registry schemas, templates, fixtures, tests.
- **Test strategy:** Valid/invalid CSV and deterministic identity cases.
- **Definition of done:** Separate query/prompt/comparison identities are enforced.
- **Rollback point:** Revert the Phase 2 commit.

## Phase 3: Configuration And Secret Boundaries

- **Objective:** Define non-secret YAML configuration and secret-loading boundaries.
- **Prerequisites:** Phase 2.
- **Allowed work:** Settings models, YAML examples, redaction helpers.
- **Prohibited work:** Real credentials, real calls, persisted database.
- **Files expected:** Config contracts, examples, tests.
- **Test strategy:** Missing-secret, redaction, and configuration validation tests.
- **Definition of done:** Secrets cannot enter config files or logs by design.
- **Rollback point:** Revert the Phase 3 commit.

## Phase 4: Evidence Storage Contracts

- **Objective:** Define immutable raw evidence manifests and file safety rules.
- **Prerequisites:** Phase 3.
- **Allowed work:** File contracts, checksums, atomic-write helpers, fixtures.
- **Prohibited work:** Provider collection and DuckDB schema creation.
- **Files expected:** Raw manifest models, storage utilities, tests.
- **Test strategy:** Immutability, checksum, collision, and corruption tests.
- **Definition of done:** Unknown payloads can be retained without interpretation.
- **Rollback point:** Revert the Phase 4 commit.

## Phase 5: Verified SERP API Evidence

- **Objective:** Populate approved SERP evidence only from official documentation.
- **Prerequisites:** Phase 4 and evidence review.
- **Allowed work:** Evidence-register updates and reviewed fixtures.
- **Prohibited work:** Guessing contracts or enabling collection.
- **Files expected:** Evidence register updates, source citations, sanitized fixtures.
- **Test strategy:** Documentation-review checklist and fixture provenance checks.
- **Definition of done:** Google/Bing/Yahoo scope is explicitly verified or blocked.
- **Rollback point:** Revert the Phase 5 commit.

## Phase 6: SERP Adapter Contracts

- **Objective:** Implement separate Live and Standard adapter interfaces from verified evidence.
- **Prerequisites:** Phase 5.
- **Allowed work:** HTTP contracts, request identity, mocked clients.
- **Prohibited work:** Real calls, LLM adapter code, parsers beyond envelope validation.
- **Files expected:** SERP contracts/adapters, respx tests.
- **Test strategy:** Mocked request construction, retry eligibility, no-network tests.
- **Definition of done:** Each retrieval method has an isolated contract.
- **Rollback point:** Revert the Phase 6 commit.

## Phase 7: SERP Collection And Raw Capture

- **Objective:** Add explicitly invoked, guarded SERP collection.
- **Prerequisites:** Phase 6, approved budgets.
- **Allowed work:** Collection orchestration, immutable capture, reconciliation.
- **Prohibited work:** dbt transformations, dashboard writes.
- **Files expected:** Collectors, CLI, audit logs, tests.
- **Test strategy:** Mocked success/failure/timeout/duplicate scenarios.
- **Definition of done:** Capture preserves raw evidence and cost safeguards.
- **Rollback point:** Disable CLI and revert Phase 7 commit.

## Phase 8: SERP Parsing And Quarantine

- **Objective:** Parse verified organic SERP structures per engine.
- **Prerequisites:** Phase 7 fixtures.
- **Allowed work:** Engine parsers, normalized contracts, quarantine handling.
- **Prohibited work:** Silent unknown-item dropping and cross-source metrics.
- **Files expected:** Parsers, fixtures, parser tests.
- **Test strategy:** Known types, unknown types, malformed envelope tests.
- **Definition of done:** Every input is parsed or quarantined with traceability.
- **Rollback point:** Retain raw evidence; revert parser commit.

## Phase 9: Verified LLM API Evidence

- **Objective:** Verify DataForSEO LLM Scraper contract and platform/model support.
- **Prerequisites:** Phase 4 and official evidence.
- **Allowed work:** Evidence-register updates and sanitized reviewed fixtures.
- **Prohibited work:** Endpoint guessing or collection enablement without verification.
- **Files expected:** Evidence register updates, reviewed fixtures.
- **Test strategy:** Evidence completeness review.
- **Definition of done:** Exact contract is verified or an explicit blocker remains.
- **Rollback point:** Revert Phase 9 commit.

## Phase 10: LLM Adapter And Collection

- **Objective:** Implement approved LLM adapter and controlled raw capture.
- **Prerequisites:** Phase 9, approved budgets.
- **Allowed work:** Separate LLM contracts, collectors, citations/source capture.
- **Prohibited work:** Shared SERP parser, dashboard actions.
- **Files expected:** LLM adapter/collector, respx tests.
- **Test strategy:** Mocked response, timeout, duplicate, and redaction tests.
- **Definition of done:** Raw model response and metadata are retained distinctly.
- **Rollback point:** Disable collection and revert Phase 10 commit.

## Phase 11: LLM Parsing And Quarantine

- **Objective:** Normalize verified model/platform evidence.
- **Prerequisites:** Phase 10 fixtures.
- **Allowed work:** Target-specific parsers, citation/source/mention contracts.
- **Prohibited work:** Unverified field assumptions or dropping unknown content.
- **Files expected:** Parsers, fixtures, tests.
- **Test strategy:** Per-target known/unknown schema tests.
- **Definition of done:** Parser provenance and quarantine are complete.
- **Rollback point:** Revert parser commit while retaining raw evidence.

## Phase 12: DuckDB And dbt Foundation

- **Objective:** Establish controlled DuckDB schema and dbt project.
- **Prerequisites:** Phases 8 and 11 contracts.
- **Allowed work:** Database lifecycle, dbt sources, Bronze/Silver models and tests.
- **Prohibited work:** API calls in dbt or dashboard reading non-presentation tables.
- **Files expected:** dbt project, migrations/bootstrap tooling, tests.
- **Test strategy:** Isolated local DuckDB/dbt test build.
- **Definition of done:** SQL transformations are owned exclusively by dbt.
- **Rollback point:** Restore prior database snapshot and revert commit.

## Phase 13: Gold Metrics And Comparison Mapping

- **Objective:** Build metric models using only approved comparison mappings.
- **Prerequisites:** Phase 12 and populated comparison registry.
- **Allowed work:** Gold SQL models, metric versioning, availability/status logic.
- **Prohibited work:** Implicit query/prompt matching.
- **Files expected:** Gold models, dbt tests, metric documentation.
- **Test strategy:** Numerator/denominator and no-data/unsupported tests.
- **Definition of done:** Metrics preserve required values and mapping provenance.
- **Rollback point:** Revert Gold models and use prior release.

## Phase 14: Release Management And Presentation Views

- **Objective:** Define completed-release checks and approved views.
- **Prerequisites:** Phase 13.
- **Allowed work:** Release manifest, presentation dbt views, completeness validation.
- **Prohibited work:** Streamlit collection/build triggers.
- **Files expected:** Release contracts, presentation models, tests.
- **Test strategy:** Incomplete-release rejection tests.
- **Definition of done:** Presentation layer is release-scoped and read-only.
- **Rollback point:** Point consumers at prior completed release.

## Phase 15: Streamlit Reporting

- **Objective:** Deliver a read-only dashboard for approved presentation views.
- **Prerequisites:** Phase 14.
- **Allowed work:** Streamlit pages, display filters, status messaging.
- **Prohibited work:** Collection, dbt builds, writes, or direct raw/Bronze/Silver reads.
- **Files expected:** Streamlit app, UI tests where practical.
- **Test strategy:** Presentation-view-only and incomplete-release tests.
- **Definition of done:** Dashboard accurately distinguishes absence from unavailable evidence.
- **Rollback point:** Disable dashboard release and revert Phase 15 commit.

## Phase 16: Hardening And Operational Acceptance

- **Objective:** Validate end-to-end controls, documentation, and release operations.
- **Prerequisites:** Phases 1-15.
- **Allowed work:** Security review, cost-control exercises, recovery drills, acceptance records.
- **Prohibited work:** Scope expansion without a new decision.
- **Files expected:** Acceptance records, runbooks, final risk review.
- **Test strategy:** Full mocked pipeline, recovery and release rollback drills.
- **Definition of done:** All acceptance criteria, controls, and known limitations are signed off.
- **Rollback point:** Maintain previous approved release and documented recovery plan.