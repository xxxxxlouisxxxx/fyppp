"""Fail when likely non-placeholder DataForSEO credentials appear in source files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
ALLOWED_TEST_FIXTURE = Path("tests/unit/test_logging_redaction.py")
PATTERN = re.compile(r"DATAFORSEO_(?:LOGIN|PASSWORD)\s*=\s*(?!replace-with-)[^\s#]+")


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or EXCLUDED & set(path.parts):
            continue
        if path.name == ".env":
            continue
        if path.relative_to(ROOT) == ALLOWED_TEST_FIXTURE:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PATTERN.search(content):
            findings.append(str(path.relative_to(ROOT)))
    if findings:
        print("Potential credentials found: " + ", ".join(sorted(findings)))
        return 1
    print("Secret scan passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
