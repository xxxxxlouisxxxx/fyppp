"""Logging setup that prevents common credential values reaching log output."""

from __future__ import annotations

import logging
import re
from typing import Final

_REDACTION_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)\b(DATAFORSEO_(?:LOGIN|PASSWORD)\s*[:=]\s*)[^\s&]+"),
    re.compile(r"(?i)(Authorization\s*:\s*)(?:Basic|Bearer)\s+[^\s,;]+"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]+"),
    re.compile(
        r"(?i)([?&](?:api[_-]?key|token|access_token|password|secret)=[^&#\s]*)"
    ),
)


class CredentialRedactionFilter(logging.Filter):
    """Replace common credential representations before a record is emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in _REDACTION_PATTERNS:
            if pattern.pattern.startswith("(?i)([?&]"):
                message = pattern.sub(
                    lambda match: f"{match.group(1).split('=')[0]}=[REDACTED]",
                    message,
                )
            elif pattern.groups == 0:
                message = pattern.sub("Basic [REDACTED]", message)
            else:
                message = pattern.sub(r"\1[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(logger_name: str = "geo_research") -> logging.Logger:
    """Configure and return a logger with credential redaction enabled."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    if not any(isinstance(item, CredentialRedactionFilter) for item in logger.filters):
        logger.addFilter(CredentialRedactionFilter())
    return logger
