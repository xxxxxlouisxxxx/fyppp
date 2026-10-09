# GEO Research Platform

Local-first research tooling for preserved SERP and generative-engine evidence. Phase 1 provides only repository foundations, safe configuration, paths, logging redaction, and a diagnostic CLI. It performs no API collection, creates no database, and contains no dbt or Streamlit implementation.

## Local Setup

Prerequisites: Python 3.12 and `uv`.

```powershell
uv python install 3.12
uv sync --all-groups
Copy-Item .env.example .env
```

Populate `.env` locally only when credentials are available. Do not place credentials in YAML files, tests, fixtures, or Git.

## Validation

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run geo-research version
uv run geo-research config-check
uv run geo-research paths
git status --short
```

The `config-check` command reports non-secret configuration only. It does not print credential values.