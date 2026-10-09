from __future__ import annotations

from pathlib import Path

from geo_research.cli import main
from geo_research.collection.preflight import Phase6Preflight


def test_unverified_evidence_blocks_real_api_before_execution(tmp_path: Path) -> None:
    register = tmp_path / "api_evidence_register.md"
    register.write_text(
        "## Google Organic SERP\n\n- Verification status: unverified\n",
        encoding="utf-8",
    )

    result = Phase6Preflight(register, ci_environment=False).check(
        target="Google Organic SERP",
        allow_real_api=True,
        dry_run=False,
        max_cost_usd=1.0,
        kill_switch_enabled=False,
        credentials_configured=True,
    )

    assert result.allowed is False
    assert "capability evidence is not verified" in result.reasons


def test_real_api_requires_explicit_opt_in_cap_and_non_ci_environment(
    tmp_path: Path,
) -> None:
    register = tmp_path / "api_evidence_register.md"
    register.write_text(
        """## Google Organic SERP

- Official documentation URL: https://example.invalid/docs
- Endpoint: /verified
- HTTP method: POST
- Required request fields: keyword
- Response-envelope fields: tasks
- Pricing evidence: https://example.invalid/pricing
- Verification status: verified
""",
        encoding="utf-8",
    )

    result = Phase6Preflight(register, ci_environment=True).check(
        target="Google Organic SERP",
        allow_real_api=True,
        dry_run=False,
        max_cost_usd=None,
        kill_switch_enabled=False,
        credentials_configured=True,
    )

    assert result.allowed is False
    assert "CI environment refuses --allow-real-api" in result.reasons
    assert "a positive --max-cost-usd is required" in result.reasons


def test_google_task_post_smoke_dry_run_builds_without_an_http_call(
    capsys,
) -> None:
    exit_code = main(
        [
            "smoke",
            "google-organic-task-post",
            "--keyword",
            "example",
            "--max-cost-usd",
            "0.01",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert '"http_calls": 0' in capsys.readouterr().out
