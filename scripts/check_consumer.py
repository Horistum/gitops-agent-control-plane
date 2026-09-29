#!/usr/bin/env python3
"""Test this core against an exact local, trusted consumer checkout without editing it.

Runs the consumer's tests in a temporary Git archive with a temporary, accurately
locked core snapshot. This is source compatibility evidence, not a release or a
live-provider test. The consumer's test code must be trusted by the operator.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from sync_control_core import LOCK, PACKAGES, TOOLING, check, inventory, metadata, safe_file, sync

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def archive(consumer, commit, destination):
    data = subprocess.check_output(["git", "-C", str(consumer), "archive", "--format=tar", commit])
    with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
                raise ValueError("Unsafe consumer archive path")
            target = destination / path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.extractfile(member).read())
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
            else:
                raise ValueError("Consumer contract gate refuses symlinks and special files")


def overlay_snapshot(source, target, snapshot):
    """Replace portable source only in the already isolated consumer archive.

    A compatibility experiment deliberately tests different bytes from the
    consumer's lock. Do not relax normal sync's protection of unmanaged work.
    """
    replaced = []
    for relative in (*PACKAGES, *TOOLING, LOCK):
        path = safe_file(target, relative)
        if path.exists():
            replaced.append(relative)
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    sync(source, target, snapshot)
    return replaced


def check_consumer(consumer, commit, output, *, timeout=900):
    consumer, output = consumer.resolve(), output.resolve()
    if type(timeout) is not int or not 1 <= timeout <= 7200:
        raise ValueError("Test timeout must be between 1 and 7200 seconds")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full consumer commit SHA is required")
    if git(consumer, "rev-parse", "HEAD") != commit or git(consumer, "status", "--porcelain"):
        raise ValueError("Consumer must be the exact clean reviewed checkout")
    if any(output == root or root in output.parents for root in (consumer, ROOT.resolve())):
        raise ValueError("Write the compatibility report outside both source checkouts")
    core_files = inventory(ROOT)
    with tempfile.TemporaryDirectory(prefix="core-consumer-") as directory:
        temp = Path(directory)
        source, target = temp / "reference", temp / "consumer"
        source.mkdir(); target.mkdir()
        archive(consumer, commit, target)
        for relative in core_files:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, path)
        if inventory(source) != core_files:
            raise ValueError("Core changed while taking compatibility snapshot")
        git(source, "init", "-b", "main")
        git(source, "config", "user.name", "Core compatibility gate")
        git(source, "config", "user.email", "contract-test@example.invalid")
        git(source, "add", ".")
        git(source, "-c", "commit.gpgsign=false", "commit", "-m", "Exact core compatibility snapshot")
        snapshot = git(source, "rev-parse", "HEAD")
        replaced = overlay_snapshot(source, target, snapshot)
        command = [sys.executable, "-S", "-m", "unittest", "discover", "-s", "tests", "-v"]
        env = {**os.environ, "PYTHONPATH": str(target), "PYTHONDONTWRITEBYTECODE": "1"}
        preparation = []
        manifest = target / "RELEASE-MANIFEST.json"
        exit_code, stdout, stderr = 0, "", ""
        if manifest.exists():
            builder = target / "scripts/build_release_manifest.py"
            if not builder.is_file():
                raise ValueError("Archived release manifest has no trusted source inventory builder")
            before = hashlib.sha256(manifest.read_bytes()).hexdigest()
            prepared = subprocess.run([sys.executable, "-S", str(builder)], cwd=target, env=env,
                                      capture_output=True, text=True, timeout=60)
            preparation.append({"command": [sys.executable, "-S", "scripts/build_release_manifest.py"],
                                "exit_code": prepared.returncode, "path": "RELEASE-MANIFEST.json",
                                "original_sha256": before,
                                "snapshot_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()})
            exit_code, stdout, stderr = prepared.returncode, prepared.stdout, prepared.stderr
        try:
            if exit_code == 0:
                result = subprocess.run(command, cwd=target, env=env, text=True,
                                        capture_output=True, timeout=timeout)
                exit_code = result.returncode
                stdout += result.stdout
                stderr += result.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
            stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        unchanged = inventory(target) == core_files and inventory(ROOT) == core_files
        try:
            lock_valid = check(target)["commit"] == snapshot
        except (ValueError, OSError):
            lock_valid = False
        consumer_unchanged = (git(consumer, "rev-parse", "HEAD") == commit
                              and not git(consumer, "status", "--porcelain"))
        tests = re.findall(r"^Ran (\d+) tests? in", stderr, re.MULTILINE)
        count = int(tests[-1]) if tests else 0
        report = {"schema": 1, "scope": "consumer-source-compatibility",
                  "consumer_commit": commit, "core_snapshot_commit": snapshot,
                  "core_version": metadata(ROOT)["__version__"], "core_files": core_files,
                  "command": command, "exit_code": exit_code,
                  "tests": count, "test_timeout_seconds": timeout,
                  "temporary_portable_replacements": replaced,
                  "snapshot_metadata_preparation": preparation,
                  "core_unchanged_during_tests": unchanged,
                  "snapshot_lock_valid": lock_valid,
                  "consumer_unchanged_during_tests": consumer_unchanged,
                  "passed": exit_code == 0 and count > 0 and unchanged and lock_valid and consumer_unchanged,
                  "live_provider_validation": False, "release_validation": False}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        output.with_suffix(".log").write_text(stdout + "\n" + stderr)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    report = check_consumer(args.consumer.resolve(), args.expected_commit, args.output.resolve(), timeout=args.timeout)
    print(json.dumps({k: v for k, v in report.items() if k != "core_files"}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
