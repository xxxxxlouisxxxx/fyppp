"""Strict UTF-8 CSV loading without side effects."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from geo_research.registries.validators import RegistryValidationError


def load_csv(path: Path, required_columns: Iterable[str]) -> list[dict[str, str]]:
    """Load a CSV only when its headers exactly match the declared contract."""
    try:
        # Accept plain UTF-8 and UTF-8 with BOM to keep multilingual CSVs portable.
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            actual = set(reader.fieldnames or [])
            required = set(required_columns)
            missing = required - actual
            unknown = actual - required
            if missing:
                raise RegistryValidationError(
                    f"{path.name}: missing columns: {', '.join(sorted(missing))}"
                )
            if unknown:
                raise RegistryValidationError(
                    f"{path.name}: unknown columns: {', '.join(sorted(unknown))}"
                )
            return [dict(row) for row in reader]
    except OSError as error:
        raise RegistryValidationError(f"Unable to read registry: {path}") from error
