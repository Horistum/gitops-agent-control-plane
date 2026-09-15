"""Executable external-cli/v1 reference adapter for trusted local fixtures.

Production consumers must supply OS isolation (Flow uses rootless Podman).
Expected predicates stay in this parent; candidate output is always input data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from control_plane_core.verification import evaluate_predicates, identity, validate_predicates
from .executor import LocalFixtureExecutor


def verify(workspace: Path, suite: list, executor=None) -> dict:
    if not isinstance(suite, list) or not 1 <= len(suite) <= 64:
        raise ValueError("Expected a bounded nonempty CLI fixture suite")
    executor = executor or LocalFixtureExecutor(10)
    rows, seen = [], set()
    for case in suite:
        if set(case) != {"id", "argv", "predicates"} or case["id"] in seen:
            raise ValueError("Malformed or duplicate CLI fixture")
        seen.add(case["id"]); validate_predicates(case["predicates"])
        if not isinstance(case["argv"], list) or not case["argv"] or any(not isinstance(v, str) for v in case["argv"]):
            raise ValueError("Fixture command must be an explicit argv")
        result = executor.run(case["argv"], workspace)
        verdict = evaluate_predicates(case["predicates"], {"exit_code": result.returncode, "stdout": result.stdout})
        rows.append({"id": case["id"], **verdict, "stderr_hash": hashlib.sha256(result.stderr.encode()).hexdigest()})
    return {"profile": "external-cli/v1", "runtime": "trusted-local-fixture", "security_sandbox": False,
            "suite_hash": identity(suite), "passed": all(r["passed"] for r in rows), "cases": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--trusted-fixture", action="store_true", required=True)
    args = parser.parse_args(argv)
    if args.suite.stat().st_size > 1_000_000: parser.error("Suite exceeds budget")
    report = verify(args.workspace.resolve(), json.loads(args.suite.read_text()))
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
