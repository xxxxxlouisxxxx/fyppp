# Architecture Decisions

## ADR-001: src-Based Python Repository

- **Status:** Accepted, v1.0.
- **Context:** Python import paths must not accidentally resolve local working-directory modules.
- **Decision:** All Python source will live under `src/geo_research`; scripts are thin command-line entry points.
- **Consequences:** Packaging and tests must install or reference the package deliberately.
- **Rejected alternatives:** Flat package layout; business logic in scripts.

## ADR-002: DuckDB As Local Analytical Store

- **Status:** Accepted, v1.0.
- **Context:** The platform is local-first and needs an analytical store.
- **Decision:** Use DuckDB for local analytical storage in later phases.
- **Consequences:** Multiple-writer coordination and database lifecycle controls are required.
- **Rejected alternatives:** Managed warehouse; SQLite; filesystem-only analytics.

## ADR-003: dbt Owns SQL Transformation

- **Status:** Accepted, v1.0.
- **Context:** Transformations require testable lineage and repeatability.
- **Decision:** SQL transformations reside in dbt; API collection never resides in dbt.
- **Consequences:** Python writes collection evidence; dbt produces modeled layers.
- **Rejected alternatives:** Python-only transformations; API macros in dbt.

## ADR-004: Immutable Raw Evidence

- **Status:** Accepted, v1.0.
- **Context:** Provider responses may evolve and parsers require auditability.
- **Decision:** Preserve raw requests/responses immutably with metadata and checksums.
- **Consequences:** Storage, retention, and sensitive-data policies are mandatory.
- **Rejected alternatives:** Keep only parsed fields; overwrite prior captures.

## ADR-005: Separate SERP Query And LLM Prompt Registries

- **Status:** Accepted, v1.0.
- **Context:** A keyword query and generative prompt are distinct research instruments.
- **Decision:** Maintain independent identities and CSV registries.
- **Consequences:** Cross-source comparisons require explicit mapping.
- **Rejected alternatives:** Single text registry; text-similarity matching.

## ADR-006: Separate SERP And LLM Adapter Contracts

- **Status:** Accepted, v1.0.
- **Context:** Retrieval and response semantics differ by source category.
- **Decision:** Define separate adapter contracts, clients, and parser boundaries.
- **Consequences:** Shared transport utilities must not blur source semantics.
- **Rejected alternatives:** Generic provider adapter; shared parser.

## ADR-007: Deterministic Request Identity

- **Status:** Accepted, v1.0.
- **Context:** Retries and timeout ambiguity can cause duplicate cost and evidence.
- **Decision:** Derive deterministic request identities from versioned, canonical request dimensions.
- **Consequences:** Canonicalization and collection-window rules require tests.
- **Rejected alternatives:** Random request IDs only; deduplication after collection.

## ADR-008: Engine/Model-Specific Parsers

- **Status:** Accepted, v1.0.
- **Context:** Response item structures differ across engines and models.
- **Decision:** Use explicit engine/model-specific parsers with a quarantine path for unknown structures.
- **Consequences:** Parser coverage grows with supported targets; unknown items remain available for review.
- **Rejected alternatives:** One universal parser; silently ignore unsupported items.

## ADR-009: No Real API Calls In CI

- **Status:** Accepted, v1.0.
- **Context:** CI must be repeatable and cost-free.
- **Decision:** CI uses fixtures and HTTP mocks only.
- **Consequences:** Contract verification requires a separately approved local/manual workflow.
- **Rejected alternatives:** CI smoke calls; shared production credentials.

## ADR-010: Read-Only Streamlit Dashboard

- **Status:** Accepted, v1.0.
- **Context:** Dashboard interaction must not alter evidence or incur cost.
- **Decision:** Streamlit reads approved presentation views only.
- **Consequences:** It cannot execute collection, dbt builds, or writes.
- **Rejected alternatives:** Dashboard-triggered collection; dashboard-managed transformations.

## ADR-011: Release-Based Dashboard Consumption

- **Status:** Accepted, v1.0.
- **Context:** In-progress data must not be presented as complete research.
- **Decision:** Dashboard access is scoped to an explicit completed release.
- **Consequences:** Release completeness checks and version metadata are required.
- **Rejected alternatives:** Read latest tables; dashboard queries against Bronze/Silver.

## ADR-012: Explicit Evidence Comparison Mapping

- **Status:** Accepted, v1.0.
- **Context:** Query/prompt relationships are research decisions, not textual coincidences.
- **Decision:** Only the comparison registry authorizes cross-source metric comparison.
- **Consequences:** Unmapped evidence remains independently reportable but not comparable.
- **Rejected alternatives:** Automatic semantic matching; same-text equivalence.

## Decision Log: Unresolved Questions

| ID | Question | Required decision/evidence | Owner | Status |
| --- | --- | --- | --- | --- |
| DL-001 | Exact DataForSEO LLM Scraper endpoints | Official DataForSEO documentation | Product/API owner | Blocked |
| DL-002 | ChatGPT and Gemini target identifiers | Official provider contract | Product/API owner | Blocked |
| DL-003 | Live versus Standard policy | Cost, latency, and completeness policy | Product owner | Open |
| DL-004 | Required versus optional search engines | Release scope | Product owner | Open |
| DL-005 | Required versus optional LLM platforms | Release scope | Product owner | Open |
| DL-006 | Location codes and languages | Approved market list and provider evidence | Research owner | Open |
| DL-007 | Maximum cost per request | Budget control | Financial owner | Open |
| DL-008 | Maximum cost per run | Budget control | Financial owner | Open |
| DL-009 | Maximum daily cost | Budget control | Financial owner | Open |
| DL-010 | Collection-window definition | Reproducibility and deduplication policy | Research owner | Open |
| DL-011 | Brand ownership reference | Canonical ownership source | Research owner | Open |
| DL-012 | Query-to-prompt comparison strategy | Registry governance policy | Research owner | Open |