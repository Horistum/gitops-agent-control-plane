#!/usr/bin/env python3
"""Test this core against an exact local, trusted consumer checkout without editing it.

Runs the consumer's tests in a temporary Git archive with a temporary, accurately
locked core snapshot. This is source compatibility evidence, not a release or a
live-provider test. The consumer's test code must be trusted by the operator.
"""
from __future__ import annotations

import argparse
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

from sync_control_core import inventory, metadata, sync

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


def check_consumer(consumer, commit, output):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full consumer commit SHA is required")
    if git(consumer, "rev-parse", "HEAD") != commit or git(consumer, "status", "--porcelain"):
        raise ValueError("Consumer must be the exact clean reviewed checkout")
    if output == consumer or consumer in output.parents:
        raise ValueError("Write the compatibility report outside the consumer checkout")
    core_files = inventory(ROOT)
    with tempfile.TemporaryDirectory(prefix="core-consumer-") as directory:
        temp = Path(directory)
        source, target = temp / "reference", temp / "consumer"
        source.mkdir(); target.mkdir()
        archive(consumer, commit, target)
        for relative in core_files:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, path)
        if inventory(source) != core_files:
            raise ValueError("Core changed while taking compatibility snapshot")
        git(source, "init", "-b", "main")
        git(source, "config", "user.name", "Core compatibility gate")
        git(source, "config", "user.email", "contract-test@example.invalid")
        git(source, "add", ".")
        git(source, "-c", "commit.gpgsign=false", "commit", "-m", "Exact core compatibility snapshot")
        snapshot = git(source, "rev-parse", "HEAD")
        sync(source, target, snapshot)
        command = [sys.executable, "-S", "-m", "unittest", "discover", "-s", "tests", "-v"]
        env = {**os.environ, "PYTHONPATH": str(target), "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            result = subprocess.run(command, cwd=target, env=env, text=True,
                                    capture_output=True, timeout=300)
            exit_code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
            stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        unchanged = inventory(target) == core_files and inventory(ROOT) == core_files
        tests = re.findall(r"^Ran (\d+) tests? in", stderr, re.MULTILINE)
        report = {"schema": 1, "scope": "consumer-source-compatibility",
                  "consumer_commit": commit, "core_snapshot_commit": snapshot,
                  "core_version": metadata(ROOT)["__version__"], "core_files": core_files,
                  "command": command, "exit_code": exit_code,
                  "tests": int(tests[-1]) if tests else 0,
                  "core_unchanged_during_tests": unchanged,
                  "passed": exit_code == 0 and bool(tests) and unchanged,
                  "live_provider_validation": False}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        output.with_suffix(".log").write_text(stdout + "\n" + stderr)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = check_consumer(args.consumer.resolve(), args.expected_commit, args.output.resolve())
    print(json.dumps({k: v for k, v in report.items() if k != "core_files"}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
