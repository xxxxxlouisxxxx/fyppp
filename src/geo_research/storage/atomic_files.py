"""Atomic file writes used by immutable raw storage."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4


class AtomicWriteConflictError(FileExistsError):
    """A finalized immutable artifact already exists."""


def atomic_write_new(path: Path, content: bytes) -> None:
    """Write a new file through a sibling temporary file and atomic rename."""
    if path.exists():
        raise AtomicWriteConflictError(f"Immutable file already exists: {path}")
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise AtomicWriteConflictError(f"Immutable file already exists: {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
