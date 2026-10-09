# Extraction completion audit — 2026-10-05

## Scope and definitions

- Compared the current active CSV assignments, queries/prompts and targets in `config/registries` against `data/warehouse/geo_research.duckdb`, collection window `2026-10` (the local records were collected on 2026-10-04).
- Counted unique query/prompt + target assignments, not API request rows. Task submission and retrieval are separate request rows and must not be double-counted.
- **Retrieved**: a locally saved response contains a `retrieval` task with status code `20000` and a non-empty `result`.
- **Pending retrieval**: submission is recorded, but no such locally saved retrieval result was found. This does not establish whether the provider is still processing, has failed, or already has a result available.
- **Not submitted**: no local request record for the assignment in this collection window. Remote-only tasks are outside this read-only audit.
- All indexed response files examined for the configured October assignments existed. This is not a complete checksum/orphan-file audit, nor a transformation/dbt completion audit.
- No provider API calls were made, no paid tasks were submitted, and no raw evidence or database records were changed.

## Summary

| Source | Configured assignments | Retrieved | Pending retrieval | No local submission |
| --- | ---: | ---: | ---: | ---: |
| Google SERP | 1,360 | 1,001 | 359 | 0 |
| Bing SERP | 1,360 | 0 | 204 | 1,156 |
| Yahoo SERP | 1,360 | 0 | 0 | 1,360 |
| Baidu SERP | 136 | 0 | 0 | 136 |
| **SERP total** | **4,216** | **1,001** | **563** | **2,652** |
| ChatGPT | 340 | 329 | 11 | 0 |
| Gemini | 340 | 269 | 71 | 0 |
| **LLM total** | **680** | **598** | **82** | **0** |
| **Overall** | **4,896** | **1,599** | **645** | **2,652** |

## SERP: no local submission

All configured assignments for the following targets have no October submission record. Ranges are inclusive numeric ID suffixes; e.g. `133-136` means `search-target-133` through `search-target-136`. Use the assignment CSV rather than a Cartesian product of all queries and targets.

| Engine | Target suffixes | Missing assignments |
| --- | --- | ---: |
| Bing | 133-136, 141-156, 161-176, 181-196, 221-236 | 1,156 |
| Yahoo | 241-256, 261-276, 281-296, 301-316, 341-356 | 1,360 |
| Baidu | 361-368 | 136 |

Bing: US (`2840`) Indonesian (`id`), plus all configured languages for UK (`2344`), China (`2156`), Singapore (`2702`) and Indonesia (`2360`) remain unsubmitted locally. Yahoo: all configured assignments. Baidu: all configured simplified-Chinese assignments for locations `1022735` and `2156`.

## SERP: pending retrieval

### Bing — 204

All configured assignments for `search-target-121` through `search-target-132` are pending: US (`2840`), English, traditional Chinese and simplified Chinese, across the configured device/OS combinations.

**Confirmed local retrieval selection issue:** `bronze.api_requests.search_engine` stores these 204 tasks as `Bing`, but `RawEvidenceRepository.pending_standard_serp_tasks()` filters with `search_engine IN ('google', 'bing', 'yahoo', 'baidu')`. That case-sensitive filter excludes these tasks. Fix/normalize this selection before attempting Bing retrieval; do not re-post these accepted tasks merely because they are absent from the pending selection.

### Google — 359

The following table is the complete pending list. Query suffix ranges are inclusive: `016` means `query-016`.

| Search target suffix | Pending query suffixes |
| --- | --- |
| 003 | 016 |
| 006 | 028 |
| 007 | 024, 033 |
| 009 | 041 |
| 010 | 041, 044, 051 |
| 011 | 044, 046 |
| 012 | 044, 050 |
| 013 | 063 |
| 014 | 056 |
| 015 | 060 |
| 016 | 056 |
| 023 | 007 |
| 024 | 007 |
| 025 | 034 |
| 026 | 028, 034 |
| 030 | 049 |
| 031 | 038 |
| 032 | 051 |
| 033 | 054 |
| 034 | 052, 066 |
| 035 | 066 |
| 036 | 055 |
| 041 | 015 |
| 042 | 013 |
| 043 | 013 |
| 044 | 013 |
| 047 | 034 |
| 048 | 024 |
| 052 | 047 |
| 053 | 056 |
| 054 | 054, 056 |
| 062 | 007 |
| 063 | 006, 012 |
| 066 | 023 |
| 067 | 023, 026 |
| 070 | 049 |
| 071 | 037, 046, 048 |
| 072 | 048-049, 051 |
| 073 | 052, 058, 061, 063, 066 |
| 074 | 052, 063 |
| 075 | 054-055, 059-063, 065-068 |
| 076 | 052-068 |
| Each of 101-104 | 001-017 |
| Each of 105-108 | 018-034 |
| Each of 109-112 | 035-051 |
| Each of 113-116 | 052-068 |

Targets `101-116` are Indonesia (`2360`): all 272 assignments remain pending. The other 87 pending Google assignments are spread across US, UK, China and Singapore.

## LLM: pending retrieval — 82

All 680 configured LLM assignments have a local submission. Only the following lack saved retrieval results. Prompt suffix ranges are inclusive: `008` means `prompt-008`.

| LLM target | Platform | Location | Language | Pending | Prompt suffixes |
| --- | --- | --- | --- | ---: | --- |
| llm-target-009 | ChatGPT | UK / 2344 | en | 4 | 008, 013, 014, 016 |
| llm-target-017 | ChatGPT | China / 2156 | en | 1 | 012 |
| llm-target-018 | ChatGPT | China / 2156 | zh-TW | 2 | 018, 029 |
| llm-target-019 | ChatGPT | China / 2156 | zh-CN | 1 | 043 |
| llm-target-020 | ChatGPT | China / 2156 | id | 3 | 057, 063, 064 |
| llm-target-021 | Gemini | China / 2156 | en | 1 | 008 |
| llm-target-024 | Gemini | China / 2156 | id | 1 | 067 |
| llm-target-029 | Gemini | Singapore / 2702 | en | 1 | 010 |
| llm-target-030 | Gemini | Singapore / 2702 | zh-TW | 1 | 025 |
| llm-target-032 | Gemini | Singapore / 2702 | id | 1 | 062 |
| llm-target-037 | Gemini | Indonesia / 2360 | en | 15 | 003-017 |
| llm-target-038 | Gemini | Indonesia / 2360 | zh-TW | 17 | 018-034 |
| llm-target-039 | Gemini | Indonesia / 2360 | zh-CN | 17 | 035-051 |
| llm-target-040 | Gemini | Indonesia / 2360 | id | 17 | 052-068 |

## Suggested next steps (not executed)

1. Correct the case-sensitive Bing pending-task selection.
2. Retrieve/reconcile the **645 already submitted** SERP + LLM assignments first. Provider-side status needs an API check; local pending is not proof of failure.
3. Review budget and provider-side reconciliation before submitting the **2,652 assignments with no local submission record**.
4. Re-audit after retrieval, then separately check parsing, transformations and dbt completion if needed.