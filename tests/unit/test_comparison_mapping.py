"""User-approved instrument scope and result-driven candidate boundaries."""

import csv
import json
from pathlib import Path

import pytest

from geo_research.registries.validators import (
    RegistryValidationError,
    load_comparisons,
    validate_registries,
)
from geo_research.transforms.brand_discovery import discover_explicit_brands
from tests.unit.test_registry_validation import write_registries

ROOT = Path(__file__).resolve().parents[2]


def test_actual_68_approved_index_mappings():
    mappings = load_comparisons(ROOT / "config/registries")
    assert len(mappings) == 68
    for index, row in enumerate(mappings, 1):
        assert row.query_id == f"query-{index:03}"
        assert row.prompt_id == f"prompt-{index:03}"
        assert row.active and row.reviewer == "requesting-user"
        assert row.scope == "matched_locale_window"


def _mapping(directory, changes=None, duplicate=False):
    with (ROOT / "config/registries/comparisons.csv").open(
        encoding="utf-8", newline="",
    ) as handle:
        row = next(csv.DictReader(handle))
    row.update(query_id="query-1", prompt_id="prompt-1")
    row.update(changes or {})
    with (directory / "comparisons.csv").open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
        if duplicate:
            writer.writerow({**row, "comparison_id": "comparison-002"})


def test_optional_legacy_registry_and_valid_approval(tmp_path):
    directory = write_registries(tmp_path)
    assert "comparisons" not in validate_registries(directory).counts
    _mapping(directory)
    assert validate_registries(directory).counts["comparisons"] == 1


@pytest.mark.parametrize("changes", [
    {"query_id": "query-missing"}, {"prompt_id": "prompt-missing"},
    {"reviewer": " "}, {"reason": ""}, {"scope": "any_locale"},
    {"effective_end_date": "2020-01-01"},
])
def test_invalid_approval_fails_closed(tmp_path, changes):
    directory = write_registries(tmp_path)
    _mapping(directory, changes)
    with pytest.raises(RegistryValidationError):
        validate_registries(directory)


def test_duplicate_active_pair_rejected(tmp_path):
    directory = write_registries(tmp_path)
    _mapping(directory, duplicate=True)
    with pytest.raises(RegistryValidationError, match="duplicate active"):
        validate_registries(directory)


def test_result_discovery_not_limited_to_fixed_brand_dictionary():
    item = dict(
        item_kind="product", observation_id="obs", result_id="result",
        item_id="item", json_path="$.items[0]",
        raw_evidence_json=json.dumps({"brand": "Previously Unknown Label"}),
    )
    result = discover_explicit_brands([item])
    assert result[0]["candidate_name"] == "Previously Unknown Label"
    assert result[0]["review_status"] == "candidate"
    assert result[0]["item_id"] == "item"
    assert "brand_id" not in result[0] and "domain" not in result[0]
    assert discover_explicit_brands([{
        **item, "item_kind": "answer_text",
        "raw_evidence_json": json.dumps({"text": "Unknown Label"}),
    }]) == []
    assert discover_explicit_brands([{
        **item, "raw_evidence_json": json.dumps({"merchant": "Not A Brand"}),
    }]) == []