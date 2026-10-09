from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from geo_research.cli import main
from geo_research.registries.validators import (
    RegistryValidationError,
    validate_registries,
)

HEADERS = {
    "queries.csv": [
        "query_id",
        "keyword",
        "language",
        "market",
        "active",
    ],
    "search_targets.csv": [
        "search_target_id",
        "provider",
        "search_engine",
        "search_type",
        "retrieval_method",
        "location_code",
        "language_code",
        "device",
        "operating_system",
        "depth",
        "active",
    ],
    "llm_prompts.csv": [
        "prompt_id",
        "prompt_text",
        "language",
        "market",
        "active",
    ],
    "llm_targets.csv": [
        "llm_target_id",
        "provider",
        "platform",
        "model_name",
        "endpoint_name",
        "location_code",
        "language_code",
        "active",
    ],
    "query_target_assignments.csv": [
        "assignment_id",
        "query_id",
        "search_target_id",
        "active",
    ],
    "prompt_target_assignments.csv": [
        "assignment_id",
        "prompt_id",
        "llm_target_id",
        "active",
    ],
    "brands.csv": [
        "brand_id",
        "canonical_name",
        "ownership_type",
        "market",
        "language",
        "effective_start_date",
        "effective_end_date",
        "active",
    ],
    "brand_aliases.csv": [
        "brand_alias_id",
        "brand_id",
        "alias_text",
        "market",
        "language",
        "effective_start_date",
        "effective_end_date",
    ],
    "brand_domains.csv": [
        "brand_domain_id",
        "brand_id",
        "domain",
        "market",
        "language",
        "effective_start_date",
        "effective_end_date",
    ],
}

ROWS = {
    "queries.csv": [
        [
            "query-1",
            "research platform",
            "en",
            "US",
            "true",
        ]
    ],
    "search_targets.csv": [
        [
            "target-1",
            "dataforseo",
            "google",
            "organic",
            "TO_BE_VERIFIED",
            "2840",
            "en",
            "desktop",
            "windows",
            "10",
            "true",
        ]
    ],
    "llm_prompts.csv": [
        [
            "prompt-1",
            "Which research platform is best?",
            "en",
            "US",
            "true",
        ]
    ],
    "llm_targets.csv": [
        [
            "llm-1",
            "dataforseo",
            "chatgpt",
            "TO_BE_VERIFIED",
            "TO_BE_VERIFIED",
            "2840",
            "en",
            "true",
        ]
    ],
    "query_target_assignments.csv": [
        ["query-assignment-1", "query-1", "target-1", "true"]
    ],
    "prompt_target_assignments.csv": [
        ["prompt-assignment-1", "prompt-1", "llm-1", "false"]
    ],
    "brands.csv": [
        ["brand-1", "Cafe Example", "owned", "US", "en", "2026-01-01", "", "true"]
    ],
    "brand_aliases.csv": [
        ["alias-1", "brand-1", "Cafe Example", "US", "en", "2026-01-01", ""]
    ],
    "brand_domains.csv": [
        ["domain-1", "brand-1", "example.test", "US", "en", "2026-01-01", ""]
    ],
}


def write_registries(
    tmp_path: Path, rows: dict[str, list[list[str]]] | None = None
) -> Path:
    registry_dir = tmp_path / "registries"
    registry_dir.mkdir()
    source_rows = ROWS if rows is None else rows
    for filename, headers in HEADERS.items():
        with (registry_dir / filename).open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(source_rows[filename])
    return registry_dir


def test_valid_registries_produce_machine_readable_result(tmp_path: Path) -> None:
    result = validate_registries(write_registries(tmp_path))

    assert result.valid is True
    assert result.counts["queries"] == 1
    assert result.counts["query_target_assignments"] == 1
    assert result.assignment_summary["search_engine"] == {"google": 1}
    assert result.model_dump(mode="json")["valid"] is True


def test_uppercase_boolean_literals_are_accepted(tmp_path: Path) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    rows["search_targets.csv"][0][-1] = "TRUE"
    rows["search_targets.csv"][0][6] = "zh-TW"

    assert validate_registries(write_registries(tmp_path, rows)).valid


def test_cli_assignment_summary_aggregates_without_prompt_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_dir = write_registries(tmp_path)

    exit_code = main(["registry", "summary", "--directory", str(registry_dir)])

    output = capsys.readouterr().out
    summary = json.loads(output)
    assert exit_code == 0
    assert summary["assignment_summary"]["provider"] == {"dataforseo": 2}
    assert "Which research platform is best?" not in output


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        (
            "queries.csv",
            lambda rows: rows["queries.csv"].append(ROWS["queries.csv"][0]),
            "duplicate",
        ),
        ("queries.csv", lambda rows: rows["queries.csv"][0].pop(), "columns"),
        (
            "queries.csv",
            lambda rows: rows["queries.csv"][0].__setitem__(-1, "yes"),
            "boolean",
        ),
        (
            "search_targets.csv",
            lambda rows: rows["search_targets.csv"][0].__setitem__(1, "google"),
            "provider",
        ),
        (
            "llm_targets.csv",
            lambda rows: rows["llm_targets.csv"][0].__setitem__(3, "gpt-unverified"),
            "model_name",
        ),
    ],
)
def test_invalid_row_contracts_fail(
    tmp_path: Path, filename: str, mutate, message: str
) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    mutate(rows)
    registry_dir = write_registries(tmp_path, rows)
    if message == "columns":
        path = registry_dir / filename
        content = path.read_text(encoding="utf-8").replace(",active\n", "\n", 1)
        path.write_text(content, encoding="utf-8")

    with pytest.raises(RegistryValidationError, match=message):
        validate_registries(registry_dir)


def test_unknown_columns_fail(tmp_path: Path) -> None:
    registry_dir = write_registries(tmp_path)
    path = registry_dir / "queries.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("\n", ",unexpected\n", 1),
        encoding="utf-8",
    )

    with pytest.raises(RegistryValidationError, match="unknown"):
        validate_registries(registry_dir)


@pytest.mark.parametrize("obsolete_column", ["endpoint_name", "serp_function"])
def test_search_target_rejects_non_execution_metadata(
    tmp_path: Path, obsolete_column: str
) -> None:
    registry_dir = write_registries(tmp_path)
    path = registry_dir / "search_targets.csv"
    content = path.read_text(encoding="utf-8")
    path.write_text(
        content.replace("search_type,", f"search_type,{obsolete_column},", 1),
        encoding="utf-8",
    )

    with pytest.raises(RegistryValidationError, match="unknown"):
        validate_registries(registry_dir)


@pytest.mark.parametrize(
    ("filename", "row_index", "message"),
    [
        ("query_target_assignments.csv", 1, "query_id"),
        ("query_target_assignments.csv", 2, "search_target_id"),
        ("prompt_target_assignments.csv", 1, "prompt_id"),
        ("prompt_target_assignments.csv", 2, "llm_target_id"),
    ],
)
def test_assignment_foreign_keys_fail(
    tmp_path: Path, filename: str, row_index: int, message: str
) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    rows[filename][0][row_index] = "missing"

    with pytest.raises(RegistryValidationError, match=message):
        validate_registries(write_registries(tmp_path, rows))


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("query_target_assignments.csv", "duplicate assignment_id"),
        ("prompt_target_assignments.csv", "duplicate assignment_id"),
    ],
)
def test_duplicate_assignment_ids_fail(
    tmp_path: Path, filename: str, message: str
) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    rows[filename].append(rows[filename][0].copy())

    with pytest.raises(RegistryValidationError, match=message):
        validate_registries(write_registries(tmp_path, rows))


@pytest.mark.parametrize(
    "filename", ["query_target_assignments.csv", "prompt_target_assignments.csv"]
)
def test_duplicate_active_assignment_pairs_fail(tmp_path: Path, filename: str) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    duplicate = rows[filename][0].copy()
    duplicate[0] = f"other-{duplicate[0]}"
    duplicate[-1] = "true"
    rows[filename].append(duplicate)
    rows[filename][0][-1] = "true"

    with pytest.raises(
        RegistryValidationError, match="duplicate active assignment pair"
    ):
        validate_registries(write_registries(tmp_path, rows))


def test_active_assignment_requires_active_source_and_target(tmp_path: Path) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    rows["queries.csv"][0][-1] = "false"

    with pytest.raises(RegistryValidationError, match="active source"):
        validate_registries(write_registries(tmp_path, rows))


def test_active_assignment_requires_active_target(tmp_path: Path) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    rows["search_targets.csv"][0][-1] = "false"

    with pytest.raises(RegistryValidationError, match="active target"):
        validate_registries(write_registries(tmp_path, rows))


@pytest.mark.parametrize(
    "filename", ["query_target_assignments.csv", "prompt_target_assignments.csv"]
)
def test_assignment_unknown_columns_fail(tmp_path: Path, filename: str) -> None:
    registry_dir = write_registries(tmp_path)
    path = registry_dir / filename
    path.write_text(
        path.read_text(encoding="utf-8").replace("\n", ",unexpected\n", 1),
        encoding="utf-8",
    )

    with pytest.raises(RegistryValidationError, match="unknown"):
        validate_registries(registry_dir)


def test_active_prompt_assignment_rejects_unverified_model(tmp_path: Path) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    rows["prompt_target_assignments.csv"][0][-1] = "true"

    with pytest.raises(RegistryValidationError, match="model_name=TO_BE_VERIFIED"):
        validate_registries(write_registries(tmp_path, rows))


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (
            [
                "brand-2",
                "Cafe Example",
                "competitor",
                "US",
                "en",
                "2026-06-01",
                "",
                "true",
            ],
            "overlap",
        ),
        (
            [
                "brand-2",
                "Other",
                "owned",
                "US",
                "en",
                "2026-12-01",
                "2026-01-01",
                "true",
            ],
            "date range",
        ),
    ],
)
def test_brand_ownership_windows_are_validated(
    tmp_path: Path, row: list[str], message: str
) -> None:
    rows = {name: [item.copy() for item in values] for name, values in ROWS.items()}
    rows["brands.csv"].append(row)

    with pytest.raises(RegistryValidationError, match=message):
        validate_registries(write_registries(tmp_path, rows))


def test_utf8_unicode_brand_alias_is_preserved(tmp_path: Path) -> None:
    rows = {name: [row.copy() for row in values] for name, values in ROWS.items()}
    rows["brand_aliases.csv"][0][2] = "Café Example"

    result = validate_registries(write_registries(tmp_path, rows))

    assert result.valid is True
