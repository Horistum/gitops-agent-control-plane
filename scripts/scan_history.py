#!/usr/bin/env python3
"""Run a bounded, redacted Gitleaks scan of a complete clean Git checkout.

Only normalized finding locations are retained. Raw matches, secrets, commit
messages and scanner stderr are never copied into the report or console output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GITLEAKS_VERSION = "8.30.1"


def normalize_findings(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("Scanner report must be an array")
    result = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("Malformed scanner finding")
        commit, rule, path, line = row.get("Commit"), row.get("RuleID"), row.get("File"), row.get("StartLine")
        if (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)
                or not isinstance(rule, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", rule)
                or not isinstance(path, str) or not path or any(ord(c) < 32 for c in path)
                or type(line) is not int or line < 1):
            raise ValueError("Scanner finding lacks a valid location")
        result.append({"commit": commit, "rule": rule, "path": path, "line": line,
                       "fingerprint": f"{commit}:{path}:{rule}:{line}"})
    return result


def scan(root: Path, executable: str, output: Path) -> dict:
    root, output = root.resolve(), output.resolve()
    if output == root or root in output.parents:
        raise ValueError("Write history evidence outside the checkout")
    program = shutil.which(executable)
    if not program:
        raise ValueError("Gitleaks must be installed explicitly before scanning")
    with tempfile.TemporaryDirectory(prefix="publication-history-") as directory:
        temporary = Path(directory)
        env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR") if k in os.environ}
        env.update(HOME=str(temporary), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0")
        def git(*args):
            result = subprocess.run(["git", "--no-pager", *args], cwd=root, env=env, text=True,
                                    capture_output=True, timeout=60)
            if result.returncode:
                raise ValueError("Cannot inspect local Git history")
            return result.stdout.strip()
        if git("rev-parse", "--is-shallow-repository") != "false":
            raise ValueError("History scan refuses a shallow checkout")
        if git("status", "--porcelain"):
            raise ValueError("History scan requires a clean checkout; uncommitted files are not covered")
        head = git("rev-parse", "HEAD")
        refs = git("for-each-ref", "--format=%(refname) %(objectname)").splitlines()
        count = int(git("rev-list", "--count", "--all", "HEAD"))
        if not refs or count < 1:
            raise ValueError("History scan requires nonempty fetched refs")
        version = subprocess.run([program, "version"], text=True, capture_output=True, env=env, timeout=30)
        if version.returncode or version.stdout.strip().lstrip("v") != GITLEAKS_VERSION:
            raise ValueError("Installed scanner version differs from the reviewed CI version")
        # Explicit default configuration and empty ignores prevent ambient local
        # configuration or inline allow comments from silently hiding findings.
        config = temporary / "gitleaks.toml"
        config.write_text('[extend]\nuseDefault = true\n')
        ignores = temporary / "empty.ignore"
        ignores.write_text("")
        raw = temporary / "redacted-findings.json"
        command = [program, "git", str(root), "--log-opts=--full-history -m --all HEAD", "--redact=100",
                   "--report-format=json", "--report-path=" + str(raw), "--exit-code=10",
                   "--no-banner", "--ignore-gitleaks-allow", "--config=" + str(config),
                   "--gitleaks-ignore-path=" + str(ignores)]
        completed = subprocess.run(command, env=env, cwd=temporary, text=True,
                                   capture_output=True, timeout=300)
        if completed.returncode not in {0, 10} or not raw.is_file() or raw.stat().st_size > 10_000_000:
            raise ValueError("Scanner did not produce a complete bounded report; raw output is withheld")
        findings = normalize_findings(json.loads(raw.read_text()))
        if bool(findings) != (completed.returncode == 10):
            raise ValueError("Scanner exit status and findings disagree")
        if git("rev-parse", "HEAD") != head or git("for-each-ref", "--format=%(refname) %(objectname)").splitlines() != refs or git("status", "--porcelain"):
            raise ValueError("Git inputs changed during the history scan")
        report = {"schema": 1, "scope": "git-reachable-history", "passed": not findings,
                  "head": head, "fetched_refs": refs, "commits": count,
                  "scanner": "gitleaks", "scanner_version": GITLEAKS_VERSION,
                  "scanner_binary_sha256": hashlib.sha256(Path(program).read_bytes()).hexdigest(),
                  "findings": findings, "non_git_data_reviewed": False,
                  "deleted_or_unfetched_refs_reviewed": False, "public_visibility_authorized": False}
        output.mkdir(parents=True, exist_ok=True)
        (output / "history-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gitleaks", default="gitleaks")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = scan(ROOT, args.gitleaks, args.output)
        print(json.dumps({k: report[k] for k in ("passed", "scope", "head", "commits", "scanner_version")}, indent=2))
        print("Finding count:", len(report["findings"]))
        return 0 if report["passed"] else 1
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"History scan failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
