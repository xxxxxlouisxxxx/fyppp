# Risk Register

| Risk | Severity | Likelihood | Mitigation | Detection | Recovery owner |
| --- | --- | --- | --- | --- | --- |
| Accidental real API cost | High | Medium | Explicit local opt-in, budgets, CI network prohibition | Audit collection invocation and billing reconciliation | Collection owner |
| Duplicate billing | High | Medium | Deterministic request IDs and outcome reconciliation | Duplicate identity report | Collection owner |
| POST timeout with unknown outcome | High | Medium | Record attempt before send; reconcile before retry | Unresolved-outcome queue | Collection owner |
| Credentials committed to Git | Critical | Low | Ignore rules, secret scanning, no secrets in config | Pre-commit/CI secret scan | Security owner |
| Incompatible engine response schemas | High | Medium | Engine-specific parsers and versioned fixtures | Parser contract failures | Parser owner |
| Incompatible LLM response schemas | High | High | Target-specific parsers and verified contract evidence | Parser/quarantine monitoring | Parser owner |
| Parser silently dropping evidence | High | Medium | Mandatory unknown-item quarantine | Input/output reconciliation counts | Parser owner |
| DuckDB multiple-writer conflict | Medium | Medium | Single-writer process policy | Lock/write failure monitoring | Data platform owner |
| Corrupted raw files | High | Low | Atomic writes and checksums | Manifest verification | Data platform owner |
| Damaged previous repository contaminates rebuild | High | Medium | Isolated clean root; evidence-only review on request | Inventory and dependency review | Reconstruction owner |
| No-data misreported as brand absence | High | Medium | Availability-state contract in Gold/presentation | Semantic metric tests | Analytics owner |
| Unsupported feature misreported as absence | High | Medium | Explicit `unsupported` state | Presentation tests | Analytics owner |
| Mismatched SERP queries and LLM prompts | High | Medium | Explicit comparison registry only | Mapping validation | Research owner |
| Changing API capabilities | High | Medium | Evidence register review/versioning | Contract review cadence | API owner |
| Dashboard reads incomplete build | High | Medium | Completed-release gate and presentation-only access | Release completeness check | Release owner |