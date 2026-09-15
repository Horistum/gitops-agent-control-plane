#!/usr/bin/env python3
"""Vendor the canonical portable core from an exact local Git source revision.

Run in either repository. No network or runtime updater is involved. Changes are
ordinary reviewable source changes; --check verifies lock hashes and inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LOCK = "CONTROL-CORE.lock.json"


def inventory(root: Path) -> dict[str, str]:
    package = root / "control_plane_core"
    if package.is_symlink() or not package.is_dir():
        raise ValueError("Missing regular portable core package")
    result = {}
    for path in sorted(package.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            raise ValueError("Core symlinks are forbidden")
        if path.is_file():
            if path.suffix not in {".py", ".json", ".md"}:
                raise ValueError("Unexpected portable core file")
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result:
        raise ValueError("Empty portable core")
    return result


def check(root: Path) -> dict:
    value = json.loads((root / LOCK).read_text())
    if (value.get("schema") != 1 or value.get("repository") != "Horistum/gitops-agent-control-plane"
            or not re.fullmatch(r"[0-9a-f]{40}", value.get("commit", ""))
            or value.get("files") != inventory(root)):
        raise ValueError("Portable core differs from its reviewed source lock")
    return value


def sync(source: Path, target: Path, commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full source commit is required")
    if source == target:
        raise ValueError("Source and consumer must be separate checkouts")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--", "control_plane_core"], text=True)
    if head != commit or dirty:
        raise ValueError("Source core must match the exact clean reviewed Git commit")
    files = inventory(source)
    destination = target / "control_plane_core"
    if destination.is_symlink():
        raise ValueError("Consumer core path is a symlink")
    if destination.exists():
        check(target)
        shutil.rmtree(destination)
    for relative in files:
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, path)
    value = {"schema": 1, "repository": "Horistum/gitops-agent-control-plane",
             "commit": commit, "contract": "autonomous-control-plane/v1", "version": "1.0.0",
             "files": files}
    (target / LOCK).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return check(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path, default=ROOT)
    parser.add_argument("--commit")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        value = check(args.target.resolve())
    else:
        if args.source is None or not args.commit:
            parser.error("--source and --commit are required for synchronization")
        value = sync(args.source.resolve(), args.target.resolve(), args.commit)
    print(json.dumps({"verified": True, "commit": value["commit"], "files": len(value["files"])}))


if __name__ == "__main__":
    main()
