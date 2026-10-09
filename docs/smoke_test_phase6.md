# Phase 6 Controlled Smoke-Test Record

Date: 2026-09-25

## Preflight Result

No real provider calls were authorized or made. The API evidence register has no
verified target with complete official endpoint, method, payload, response,
pricing, location, and language evidence. The ChatGPT and Gemini targets are
explicitly blocked. Sandbox availability is therefore not assessed against an
unverified endpoint.

## Target Status

| Target | Capability state | Dry run | Real calls | Duplicate check |
| --- | --- | --- | --- | --- |
| Google Organic SERP | unverified | passed; zero calls | 0 | not applicable |
| Bing Organic SERP | unverified | passed; zero calls | 0 | not applicable |
| Yahoo Organic SERP | unverified | passed; zero calls | 0 | not applicable |
| ChatGPT LLM Scraper | blocked | passed; zero calls | 0 | not applicable |
| Gemini LLM Scraper | blocked | passed; zero calls | 0 | not applicable |

No task/request IDs, provider-reported costs, raw hashes, byte sizes, response
schemas, top-level fields, or item types exist because no request was sent.

## Executed Commands And Exit Codes

| Command | Exit code | Result |
| --- | --- | --- |
| `uv sync --all-groups` | 0 | Dependencies resolved and checked. |
| `uv run pytest` | 0 | 56 tests passed. |
| `uv run ruff check .` | 0 | Passed. |
| `uv run ruff format --check .` | 0 | Passed. |
| `uv run mypy src` | 0 | Passed for 55 source files. |
| `uv run python scripts/secret_scan.py` | 0 | Passed. |
| Google, Bing, Yahoo dry-run commands | 0 each | Each reported `http_calls: 0`. |
| ChatGPT and Gemini dry-run commands | 0 each | Each reported `http_calls: 0`. |
| CI Google real-mode refusal check | 2 | Refused before transport; `http_calls: 0`. |

## Credentials And Git State

`geo-research config-check` exited 0 and reported only Boolean credential state:
both DataForSEO credentials are not configured. No credential values were read
into command output. Git status was inspected: this is an initial `master`
repository with no commits, and all project files are untracked. No existing
working-tree change was reverted.

## Required Controls

- Real mode requires `--allow-real-api` and a positive `--max-cost-usd`.
- `GEO_RESEARCH_REAL_API_KILL_SWITCH` defaults to enabled and prevents real mode.
- A `CI` environment refuses `--allow-real-api`.
- The collection command emits zero HTTP calls until a fully verified capability
  is separately implemented.

## Fixtures

`tests/fixtures/serp` and `tests/fixtures/llm` contain only sanitized fixture
placeholders. No response fixture was created because no real response exists.