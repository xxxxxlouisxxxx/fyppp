"""Explicit local, hash-verified backup/restore into new independent directories.

Writers must be stopped. Scope is supplied by an operator, never inferred from
current registries. No database is opened, migrated, collected or published here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TypedDict, cast
from uuid import uuid4


class BackupFile(TypedDict):
    path: str
    sha256: str
    bytes: int


class BackupManifest(TypedDict):
    version: str
    reviewer: str
    reason: str
    created_at: str
    files: list[BackupFile]
    limitations: str


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(value: str) -> Path:
    parts = PurePosixPath(value)
    if (not value or parts.is_absolute() or ".." in parts.parts
            or "\\" in value or ":" in value or not parts.parts):
        raise ValueError("backup paths must be safe relative POSIX paths")
    return Path(*parts.parts)


def _independent(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("destination must not exist; live overwrite is forbidden")
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError("destination must be outside source directory")


def backup(
    root: Path,
    destination: Path,
    *,
    files: tuple[str, ...],
    reviewer: str,
    reason: str,
    writers_stopped: bool = False,
) -> BackupManifest:
    """Copy an explicit scope; abort if source bytes change during capture."""
    if not writers_stopped:
        raise ValueError("stop all writers and explicitly confirm before backup")
    if not reviewer.strip() or not reason.strip() or not files:
        raise ValueError("reviewer, reason and explicit nonempty file scope required")
    _independent(root, destination)
    entries: list[BackupFile] = []
    paths = []
    for name in files:
        relative = _relative(name)
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("scope requires existing regular files, not symlinks")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("scope escapes backup root")
        if any(part in {".env", ".git", ".venv"} for part in relative.parts):
            raise ValueError("secret/environment files are not approved backup scope")
        if any((Path(str(path) + suffix)).exists()
               for suffix in (".wal", "-wal", "-journal")):
            raise ValueError("active database journal found; stop/checkpoint writers")
        paths.append(path)
        entries.append({"path": relative.as_posix(), "sha256": _hash(path),
                        "bytes": path.stat().st_size})
    if len(set(files)) != len(files):
        raise ValueError("duplicate scope paths")
    manifest: BackupManifest = {
        "version": "local-recovery-1", "reviewer": reviewer, "reason": reason,
        "created_at": datetime.now(UTC).isoformat(), "files": entries,
        "limitations": "Operator-scoped cold backup; scope completeness not inferred.",
    }
    temporary = destination.with_name(destination.name + ".tmp-" + str(uuid4()))
    temporary.mkdir(parents=True)
    try:
        for entry, source in zip(entries, paths, strict=True):
            target = temporary / "files" / _relative(entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if _hash(target) != entry["sha256"] or _hash(source) != entry["sha256"]:
                raise ValueError("source changed during backup")
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8",
        )
        if destination.exists():
            raise ValueError("destination was created concurrently")
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary)
        raise
    return manifest


def restore(bundle: Path, destination: Path) -> BackupManifest:
    """Verify a bundle and restore to a nonexistent destination, never live paths."""
    _independent(bundle, destination)
    decoded = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(decoded, dict) or not isinstance(decoded.get("files"), list):
        raise ValueError("invalid backup manifest structure")
    for entry in decoded["files"]:
        if (not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                or not isinstance(entry.get("sha256"), str)
                or type(entry.get("bytes")) is not int):
            raise ValueError("invalid backup file manifest")
    manifest = cast(BackupManifest, decoded)
    if manifest.get("version") != "local-recovery-1" or not manifest.get("files"):
        raise ValueError("unsupported or empty backup manifest")
    seen = set()
    for entry in manifest["files"]:
        relative = _relative(entry["path"])
        source = bundle / "files" / relative
        if entry["path"] in seen:
            raise ValueError("duplicate backup paths")
        seen.add(entry["path"])
        if source.is_symlink() or not source.resolve().is_relative_to(bundle.resolve()):
            raise ValueError("backup source escapes bundle")
        if _hash(source) != entry["sha256"] or source.stat().st_size != entry["bytes"]:
            raise ValueError("backup checksum or size mismatch")
    temporary = destination.with_name(destination.name + ".tmp-" + str(uuid4()))
    temporary.mkdir(parents=True)
    try:
        for entry in manifest["files"]:
            relative = _relative(entry["path"])
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / "files" / relative, target)
            if _hash(target) != entry["sha256"]:
                raise ValueError("restore checksum mismatch")
        if destination.exists():
            raise ValueError("destination was created concurrently")
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary)
        raise
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    saving = commands.add_parser("backup")
    saving.add_argument("--root", type=Path, required=True)
    saving.add_argument("--destination", type=Path, required=True)
    saving.add_argument("--file", action="append", required=True)
    saving.add_argument("--reviewer", required=True)
    saving.add_argument("--reason", required=True)
    saving.add_argument("--writers-stopped", action="store_true")
    restoring = commands.add_parser("restore")
    restoring.add_argument("--bundle", type=Path, required=True)
    restoring.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (
            backup(args.root, args.destination, files=tuple(args.file),
                   reviewer=args.reviewer, reason=args.reason,
                   writers_stopped=args.writers_stopped)
            if args.command == "backup" else restore(args.bundle, args.destination)
        )
        print(json.dumps({"verified_files": len(result["files"])}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())