"""Read-only JSON integrity/provenance inventory; prints report, never repairs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from transform_all_raw import audit_raw, read_provenance


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "data/warehouse").glob("*.duckdb"))
    before = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in paths}
    rows = audit_raw(root / "data/raw")
    index, _, reports = read_provenance(paths)
    after = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in paths}
    verified = [row for row in rows
                if row["disposition"] == "verified_response_candidate"]
    print(json.dumps({
        "audit_scope": "all serp/llm JSON; no index repair or migration",
        "raw_json_files": len(rows),
        "directories": len({str(Path(row["path"]).parent) for row in rows}),
        "dispositions": dict(Counter(row["disposition"] for row in rows)),
        "invalid_json": sum(not row["json_valid"] for row in rows),
        "verified_response_candidates": len(verified),
        "exact_db_provenance": sum(
            bool(index.get((row["request_id"], row["sha256"]))) for row in verified
        ),
        "integrity_problems": dict(Counter(
            problem for row in rows if row["role"] == "response"
            for problem in row["integrity_problems"]
        )),
        "warehouse_hashes_unchanged": before == after,
        "warehouse_hashes_before": before, "warehouse_hashes_after": after,
        "warehouse_count": len(paths), "provenance_reports": reports,
        "limitations": (
            "JSON triples only; non-JSON/temp files and DB index orphan rows "
            "not enumerated. Verified response is not usable-feature coverage."
        ),
    }, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()