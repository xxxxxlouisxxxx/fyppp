"""Stable identifier validation helpers."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def validate_identifier(value: str) -> str:
    """Require lowercase, deterministic registry identifiers."""
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError("must be a lowercase hyphenated identifier")
    return value


RegistryIdentifier = Annotated[str, AfterValidator(validate_identifier)]
