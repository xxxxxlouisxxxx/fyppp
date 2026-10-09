"""Fail-closed Phase 6 gates before any real provider transport is permitted."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Non-secret decision data for a prospective controlled smoke test."""

    allowed: bool
    reasons: tuple[str, ...]


class Phase6Preflight:
    """Validate explicit operational controls and registered API contract evidence."""

    def __init__(self, evidence_register: Path, *, ci_environment: bool) -> None:
        self.evidence_register = evidence_register
        self.ci_environment = ci_environment

    def check(
        self,
        *,
        target: str,
        allow_real_api: bool,
        dry_run: bool,
        max_cost_usd: float | None,
        kill_switch_enabled: bool,
        credentials_configured: bool,
    ) -> PreflightResult:
        """Return every unmet real-call precondition without issuing a request."""
        if dry_run:
            return PreflightResult(True, ())

        reasons: list[str] = []
        if not allow_real_api:
            reasons.append("--allow-real-api is required")
        if self.ci_environment and allow_real_api:
            reasons.append("CI environment refuses --allow-real-api")
        if max_cost_usd is None or max_cost_usd <= 0:
            reasons.append("a positive --max-cost-usd is required")
        if kill_switch_enabled:
            reasons.append("real API kill switch is enabled")
        if not credentials_configured:
            reasons.append("provider credentials are not configured")

        fields = self._target_fields(target)
        if fields.get("verification status", "").casefold() != "verified":
            reasons.append("capability evidence is not verified")
        for required in (
            "official documentation url",
            "endpoint",
            "http method",
            "required request fields",
            "response-envelope fields",
            "pricing evidence",
        ):
            if not fields.get(required):
                reasons.append(f"missing verified evidence field: {required}")
        return PreflightResult(not reasons, tuple(reasons))

    def _target_fields(self, target: str) -> dict[str, str]:
        """Read a single Markdown target section without inventing API contracts."""
        try:
            content = self.evidence_register.read_text(encoding="utf-8")
        except OSError:
            return {}
        heading = f"## {target}"
        start = content.find(heading)
        if start < 0:
            return {}
        section = content[start + len(heading) :]
        next_heading = section.find("\n## ")
        if next_heading >= 0:
            section = section[:next_heading]
        fields: dict[str, str] = {}
        for line in section.splitlines():
            if not line.startswith("- ") or ":" not in line:
                continue
            name, value = line[2:].split(":", maxsplit=1)
            fields[name.strip().casefold()] = value.strip()
        return fields
