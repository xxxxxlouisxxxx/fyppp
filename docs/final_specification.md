# GEO Research Platform: Final Specification

## Project Purpose

Build a local-first research platform that collects, preserves, compares, and reports traditional search-engine-result-page (SERP) evidence and generative-engine-result-page (GERP) evidence for brand visibility research. DataForSEO is the API provider. It is not a search engine or an LLM platform.

## In Scope

- Organic SERP collection from Google, Bing, Yahoo, and later explicitly verified search engines through DataForSEO.
- Distinct Live and Standard SERP retrieval adapters.
- LLM evidence collection through an explicitly verified DataForSEO LLM Scraper contract.
- Separate registries for SERP queries, LLM prompts, search targets, LLM targets, brands, and approved evidence comparisons.
- Immutable raw capture; Bronze metadata; Silver parsed evidence; Gold metrics; approved presentation views.
- DuckDB storage, dbt SQL transformations, and read-only Streamlit reporting in later phases.
- Evidence availability, collection status, numerator, denominator, metric value, and metric version in reporting outputs.

## Out Of Scope

- Paid-search analysis, ranking manipulation, automated SEO recommendations, data collection through browser automation, direct scraping of Google/Bing/Yahoo/ChatGPT/Gemini, and unverified API features.
- Equating a SERP query with an LLM prompt based on similar text.
- API collection in dbt, collection/build actions from Streamlit, real calls in CI, and any schema inferred from undocumented responses.

## Source Model

Source categories are `serp` and `llm`. Provider identifies the service making the API available, initially `dataforseo`. Platform identifies the end-user system being researched, such as a search engine or LLM product. Search-engine identity is separate from platform and may be `google`, `bing`, or `yahoo`. Search type is initially `organic`.

Every collection record must retain, where applicable: `source_category`, `provider`, `platform`, `search_engine`, `search_type`, `endpoint_name`, `api_function`, `retrieval_method`, `model_name`, `location`, `language`, `device`, and `operating_system`.

## Registries

All user-managed registries will be CSV files in later phases and will have stable deterministic identifiers.

- **SERP query registry:** Query identity, query text, language/location intent, and activation state. It does not contain LLM prompts.
- **LLM prompt registry:** Prompt identity, prompt text, prompt version, intended target/model constraints, and activation state. It does not contain SERP queries.
- **Search target registry:** Explicitly verified search engines, search type, platform attributes, and allowed retrieval methods.
- **LLM target registry:** Explicitly verified LLM platforms and model identifiers supported by the approved provider contract.
- **Comparison registry:** The sole approval mechanism for comparing a query identity and a prompt identity. It records comparison purpose, version, eligibility, and rationale.
- **Brand registry:** Brand identity, canonical name, aliases, ownership reference, activation state, and matching-policy version.

## Data Layers

- **Raw:** Immutable provider request/response evidence and collection artifacts, stored outside Git.
- **Bronze:** Collection metadata and raw-file references with no undocumented interpretation.
- **Silver:** Parser-produced normalized evidence, including quarantined unknown structures.
- **Gold:** Versioned metrics retaining numerators, denominators, metric value, availability, and collection status.
- **Presentation:** Approved, release-scoped read-only views consumed by Streamlit.

## Current Release Concept

The initial release is a reproducible local research workflow: validated registries, controlled collection, immutable evidence, documented transformations, a release marker, and a dashboard that reads only approved presentation views. Phase 0 defines the contract only; it creates no runtime system.

## Data-Availability States

Every relevant result must distinguish `available`, `not_collected`, `pending`, `unsupported`, `provider_error`, `parser_quarantined`, `no_results`, and `not_applicable`. A missing collection, unsupported feature, or unavailable evidence must never be represented as brand absence.

## Security Requirements

- Credentials reside only in local secret storage or environment variables and never in Git, fixtures, logs, reports, or CSV registries.
- Raw responses, request payloads, local databases, and logs are Git-ignored in later phases.
- Logs and reports must redact credential-like material.
- All timestamps are timezone-aware UTC.

## Cost-Control Requirements

- No real API calls in Phase 0 or CI.
- Collection requires explicit cost guardrails: per-request, per-run, and daily limits before activation.
- Deterministic request identities, collection windows, and outcome reconciliation protect against duplicate billing and timeout ambiguity.
- Live and Standard retrieval policies remain blocked until evidence is approved.

## Recovery Requirements

- Raw evidence is immutable and checksummed.
- Unknown structures are retained and quarantined, not dropped.
- Releases are reproducible from versioned registries, raw evidence references, parser versions, metric versions, and dbt artifacts.
- Rollback restores the prior approved release without overwriting raw evidence.

## Definition Of Project Completion

The project is complete when verified provider contracts support controlled collections; raw, Bronze, Silver, Gold, and presentation contracts are tested; approved comparison mappings drive metrics; a release-scoped read-only dashboard reports complete availability/status semantics; security and cost controls are operational; and each phase has passed its documented acceptance criteria.