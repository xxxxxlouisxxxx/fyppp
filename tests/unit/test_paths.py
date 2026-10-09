from __future__ import annotations

from pathlib import Path

from geo_research.config.paths import RepositoryPaths


def test_paths_are_anchored_to_repository_root(monkeypatch) -> None:
    expected_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(expected_root / "docs")

    paths = RepositoryPaths.discover()

    assert paths.root == expected_root
    assert paths.raw_data == expected_root / "data" / "raw"
    assert paths.resolve(Path("data/warehouse/example.duckdb")) == (
        expected_root / "data" / "warehouse" / "example.duckdb"
    )
