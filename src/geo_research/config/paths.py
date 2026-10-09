"""Cross-platform repository paths independent of the working directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RepositoryPaths:
    """Resolved filesystem locations rooted at the installed source checkout."""

    root: Path
    config: Path
    input_data: Path
    raw_data: Path
    warehouse_data: Path
    exports_data: Path
    logs: Path

    @classmethod
    def discover(cls) -> RepositoryPaths:
        """Discover the checkout root from this module rather than the CWD."""
        root = Path(__file__).resolve().parents[3]
        data = root / "data"
        return cls(
            root=root,
            config=root / "config",
            input_data=data / "input",
            raw_data=data / "raw",
            warehouse_data=data / "warehouse",
            exports_data=data / "exports",
            logs=root / "logs",
        )

    def resolve(self, path: Path) -> Path:
        """Resolve a configured path relative to the repository root."""
        return path if path.is_absolute() else self.root / path
