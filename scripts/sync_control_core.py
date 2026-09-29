#!/usr/bin/env python3
"""Transfer committed portable source between development and reference repos.

This source operation never deploys. GitHub review remains a release gate.
Legacy core-only locks remain readable; new locks also bind optional worker
code and transfer tooling. Record portable bytes before recording their lock.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = "CONTROL-CORE.lock.json"
REFERENCE_REPOSITORY = "Horistum/gitops-agent-control-plane"
ORIGINS = "PORTABLE-ORIGINS.json"
PACKAGES = ("control_plane_core", "agent_worker")
TOOLING = ("scripts/sync_control_core.py", "scripts/check_workflow_adapters.py",
           "tests/test_portable_sync.py", "tests/test_workflow_adapter_matrix.py",
           "tests/test_agent_worker.py", "tests/fixtures/worker_app_server.py")


def repositories(root):
    """Consumer trust belongs to reviewed local configuration, not portable code."""
    path = safe_file(root, ORIGINS)
    if not path.exists(): return {REFERENCE_REPOSITORY}
    value = json.loads(path.read_text())
    rows = value.get("repositories") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or set(value) != {"schema", "repositories"} or value["schema"] != 1
            or not isinstance(rows, list) or not 1 <= len(rows) <= 16
            or any(not isinstance(row, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", row) for row in rows)):
        raise ValueError("Invalid approved portable source origins")
    return set(rows)


def metadata(root):
    result = {}
    for node in ast.parse((root / "control_plane_core/__init__.py").read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"__version__", "CONTRACT"}:
                    result[target.id] = ast.literal_eval(node.value)
    if set(result) != {"__version__", "CONTRACT"}:
        raise ValueError("Missing literal portable core metadata")
    return result


def safe_file(root, relative):
    parts = PurePosixPath(relative)
    if not relative or parts.is_absolute() or ".." in parts.parts or "\\" in relative:
        raise ValueError("Unsafe portable path")
    path = root
    for index, part in enumerate(parts.parts):
        path /= part
        if path.is_symlink():
            raise ValueError("Portable symlinks are forbidden: " + relative)
        if index < len(parts.parts) - 1 and path.exists() and not path.is_dir():
            raise ValueError("Portable path ancestor is not a directory: " + relative)
    return path


def inventory(root, *, legacy=False):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Portable source root must be a regular directory")
    result = {}
    for name in PACKAGES[:1] if legacy else PACKAGES:
        package = safe_file(root, name)
        if not package.exists() and name != "control_plane_core":
            continue
        if not package.is_dir():
            raise ValueError("Missing regular portable package: " + name)
        for path in sorted(package.rglob("*")):
            relative = path.relative_to(root).as_posix()
            safe_file(root, relative)
            if "__pycache__" in path.parts:
                continue
            if path.is_file():
                if path.suffix not in {".py", ".json", ".md"}:
                    raise ValueError("Unexpected portable file: " + relative)
                result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif not path.is_dir():
                raise ValueError("Non-regular portable entry: " + relative)
    if not legacy:
        for relative in TOOLING:
            path = safe_file(root, relative)
            if path.exists():
                if not path.is_file():
                    raise ValueError("Portable tooling must be a regular file")
                result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if "control_plane_core/__init__.py" not in result:
        raise ValueError("Empty portable core")
    return dict(sorted(result.items()))


def check(root):
    path = safe_file(root, LOCK)
    if not path.is_file():
        raise ValueError("Missing portable source lock")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Portable source lock must be an object")
    declared, schema = metadata(root), value.get("schema")
    if (type(schema) is not int or schema not in {1, 2}
            or value.get("repository") not in repositories(root)
            or not isinstance(value.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", value["commit"])
            or value.get("files") != inventory(root, legacy=schema == 1)
            or value.get("version") != declared["__version__"]
            or value.get("contract") != declared["CONTRACT"]):
        raise ValueError("Portable source differs from its committed source lock")
    if schema == 1 and value["repository"] != "Horistum/gitops-agent-control-plane":
        raise ValueError("Legacy lock has an unsupported source")
    if schema == 2:
        packages = [n for n in PACKAGES if any(p.startswith(n + "/") for p in value["files"])]
        if value.get("packages") != packages:
            raise ValueError("Portable package inventory differs from its lock")
    return value


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def snapshot(source, commit, repository):
    if repository not in repositories(source) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("An approved source repository and full commit are required")
    if git(source, "rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("Source HEAD differs from the requested commit")
    files = inventory(source)
    if git(source, "status", "--porcelain", "--untracked-files=all", "--", *PACKAGES, *TOOLING):
        raise ValueError("Portable source must match the exact clean Git commit")
    entries = {}
    for row in git(source, "ls-tree", "-rz", commit, "--", *PACKAGES, *TOOLING).split(b"\0"):
        if not row:
            continue
        meta, raw_path = row.split(b"\t", 1)
        mode, kind, object_id = meta.decode().split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Portable Git objects must be regular files")
        entries[raw_path.decode("utf-8")] = mode, object_id
    if set(entries) != set(files):
        raise ValueError("Portable inventory differs from committed Git objects")
    data = {}
    for path, expected in files.items():
        mode, object_id = entries[path]
        content = git(source, "cat-file", "blob", object_id)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Portable source changed during inspection")
        data[path] = content, 0o755 if mode == "100755" else 0o644
    declared = metadata(source)
    value = {"schema": 2, "repository": repository, "commit": commit,
             "contract": declared["CONTRACT"], "version": declared["__version__"],
             "packages": [n for n in PACKAGES if any(p.startswith(n + "/") for p in files)], "files": files}
    return value, data


def atomic_write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".portable-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def record(root, commit, repository):
    """Bind this checkout's already committed portable bytes without a cycle."""
    value, _ = snapshot(root, commit, repository)
    atomic_write(safe_file(root, LOCK), encode(value))
    return check(root)


def sync(source, target, commit, repository="Horistum/gitops-agent-control-plane",
         *, adopt_identical=False, export_only=False):
    if source.resolve() == target.resolve():
        raise ValueError("Use --record for this checkout; transfer requires separate roots")
    value, data = snapshot(source, commit, repository)
    if target.is_symlink() or not target.is_dir():
        raise ValueError("Target must be an existing regular directory")
    safe_file(target, LOCK)
    if not export_only and repository not in repositories(target):
        raise ValueError("Source origin is not approved by the target; use --export-only and record the target's reviewed commit")
    has_core = (target / "control_plane_core").exists()
    if not has_core and any(safe_file(target, p).exists() for p in PACKAGES + TOOLING):
        raise ValueError("Unmanaged partial portable target cannot be overwritten")
    existing = inventory(target) if has_core else {}
    if (target / LOCK).exists():
        try:
            previous = check(target)
            undeclared = set(existing) - set(previous["files"])
            if any(existing[p] != value["files"].get(p) for p in undeclared):
                raise ValueError("Undeclared portable additions would be overwritten")
        except ValueError:
            if not adopt_identical or existing != value["files"]:
                raise
    elif existing and (not adopt_identical or existing != value["files"]):
        raise ValueError("Unmanaged target requires --adopt-identical and byte-identical source")
    for path in set(existing) | set(data):
        destination = safe_file(target, path)
        if destination.exists() and not destination.is_file():
            raise ValueError("Portable destination is not a regular file: " + path)
    backup = {p: (safe_file(target, p).read_bytes(), safe_file(target, p).stat().st_mode & 0o777)
              for p in existing}
    old_lock = (target / LOCK).read_bytes() if (target / LOCK).exists() else None
    try:
        for path, (content, mode) in data.items():
            atomic_write(target / path, content, mode)
        for path in set(existing) - set(data):
            (target / path).unlink()
        if export_only:
            # Never publish a private development origin in a public candidate.
            # Leave the previous lock untouched until the exported bytes are
            # committed locally and --record binds that exact target commit.
            return {"exported": True, "record_required": True, "commit": commit, "files": value["files"]}
        atomic_write(target / LOCK, encode(value))
        return check(target)
    except BaseException:
        for path in set(data) - set(backup):
            safe_file(target, path).unlink(missing_ok=True)
        for path, (content, mode) in backup.items():
            atomic_write(target / path, content, mode)
        if old_lock is None:
            (target / LOCK).unlink(missing_ok=True)
        else:
            atomic_write(target / LOCK, old_lock)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path, default=ROOT)
    parser.add_argument("--commit")
    parser.add_argument("--repository", default=REFERENCE_REPOSITORY)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--record", action="store_true")
    parser.add_argument("--adopt-identical", action="store_true")
    parser.add_argument("--export-only", action="store_true", help="Copy portable bytes without recording development-origin provenance in the target")
    args = parser.parse_args(argv)
    if args.target.is_symlink() or args.source is not None and args.source.is_symlink():
        parser.error("Linked source/target roots are forbidden")
    target = args.target.resolve()
    if args.check:
        value = check(target)
    elif args.record:
        if not args.commit or args.source:
            parser.error("--record requires --commit and no --source")
        value = record(target, args.commit, args.repository)
    else:
        if args.source is None or not args.commit:
            parser.error("--source and --commit are required")
        value = sync(args.source.resolve(), target, args.commit, args.repository,
                     adopt_identical=args.adopt_identical, export_only=args.export_only)
    if args.export_only:
        print(json.dumps({"exported": True, "record_required": True,
                          "commit": value["commit"], "files": len(value["files"])}))
        return
    print(json.dumps({"verified": True, "repository": value["repository"],
                      "commit": value["commit"], "version": value["version"],
                      "files": len(value["files"])}))


if __name__ == "__main__":
    main()
