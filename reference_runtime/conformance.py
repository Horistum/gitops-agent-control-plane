from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

from . import recovery_conformance as base
from . import _conformance_impl as legacy
from .contracts import REFERENCE_CONTRACT
from .engine import run_request
from .scenarios import load_scenario, scenario_names


def _git(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result.stdout.strip()


def run_human_resume(repository_root: Path, output: Path, spec: dict) -> tuple[dict, Path]:
    if spec.get("tamper_candidate_before_decision") is not True:
        return legacy.run_human_resume(repository_root, output, spec)

    run_id = f"{spec['name']}-{int(time.time()*1000)}"
    run_dir = output / run_id
    start = legacy._run_subprocess([
        sys.executable,
        "-S",
        "-m",
        "reference_runtime.engine",
        "--repository-root",
        str(repository_root),
        "--output",
        str(output),
        "--scenario",
        spec["name"],
        "--run-id",
        run_id,
    ], repository_root)
    if start.returncode:
        raise AssertionError(f"human-tamper start process failed: {start.stderr}")

    evidence = run_dir / "evidence"
    initial = legacy._load_summary(evidence)
    if initial["status"] != "NEEDS_DECISION":
        raise AssertionError(f"human-tamper scenario did not pause first: {initial['status']}")
    state = json.loads((evidence / "state.json").read_text())
    pending = state.get("pending_decision")
    if not isinstance(pending, dict):
        raise AssertionError("human-tamper scenario has no durable pending decision")
    expected_sha = pending["candidate_sha"]
    branch = pending["candidate_branch"]

    workspace = run_dir / "workspace"
    _git(workspace, "checkout", branch)
    service = workspace / "src" / "reference_app" / "service.py"
    service.write_text(service.read_text() + "\n\ndef backdoor() -> bool:\n    return True\n")
    _git(workspace, "add", "src/reference_app/service.py")
    _git(workspace, "commit", "-m", "Tamper candidate after human review")
    tampered_sha = _git(workspace, "rev-parse", "HEAD")
    if tampered_sha == expected_sha:
        raise AssertionError("candidate tamper fixture did not move the candidate branch")

    resumed = legacy._run_subprocess([
        sys.executable,
        "-S",
        "-m",
        "reference_runtime.engine",
        "--repository-root",
        str(repository_root),
        "--resume",
        str(run_dir),
        "--decision",
        "approve",
        "--decided-by",
        "conformance-human",
    ], repository_root)
    if resumed.returncode:
        raise AssertionError(f"human-tamper resume process failed: {resumed.stderr}")
    return legacy._load_summary(evidence), evidence


def assert_scenario(spec: dict, summary: dict, evidence: Path) -> list[str]:
    checks = base.assert_scenario(spec, summary, evidence)
    name = spec["name"]

    if name == "human-approve-after-tamper":
        human = json.loads((evidence / "human-decision-example-001-attempt-01.json").read_text())
        if human.get("decision") != "approve":
            raise AssertionError("tamper scenario did not record the attempted human approval")
        if human.get("candidate_identity_matches") is not False:
            raise AssertionError("human approval did not detect candidate identity movement")
        observed = human.get("observed_candidate_sha")
        expected = human.get("candidate_sha")
        if not isinstance(observed, str) or observed == expected:
            raise AssertionError("human identity evidence did not record the moved branch tip")
        if summary.get("status") != "BLOCKED_POLICY" or summary.get("merge_sha") is not None:
            raise AssertionError("moved candidate was not blocked before merge")
        if "candidate moved after human decision was requested" not in summary.get("reason", ""):
            raise AssertionError("tamper block reason is not identity-specific")
        workspace = evidence.parent / "workspace"
        main_service = _git(workspace, "show", "main:src/reference_app/service.py")
        if "backdoor" in main_service:
            raise AssertionError("tampered candidate content reached main")
        checks += [
            "candidate branch moved after review was actually exercised",
            "human approval re-bound to observed Git branch identity",
            "moved candidate blocked before merge",
            "tampered content absent from main",
        ]

    if name == "repair-loop":
        checks = [
            check
            for check in checks
            if check != "verification feedback routed to repair"
        ]
        architect = json.loads(
            (evidence / "role-architect-example-001-attempt-02.json").read_text()
        )
        expected_ref = "feedback-example-001-attempt-01.json"
        if expected_ref not in architect.get("input_refs", []):
            raise AssertionError("second deterministic attempt does not reference prior feedback")
        checks.append(
            "feedback artifact emitted and referenced by the next bounded fixture attempt"
        )

    return checks


def run_matrix(repository_root: Path, output: Path | None = None) -> dict:
    if output is None:
        output = repository_root / ".demo" / "conformance" / time.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=True)
    base_goal = json.loads((repository_root / "examples" / "goal.example.json").read_text())
    rows: list[dict] = []
    for name in scenario_names(repository_root):
        spec = load_scenario(repository_root, name)
        row = {
            "scenario": name,
            "expected_status": spec["expected_status"],
            "expectation": spec.get("expectation", "enforced"),
            "passed": False,
            "checks": [],
        }
        try:
            if spec.get("fault_injection"):
                summary, evidence = base.run_crash_recovery(repository_root, output, spec)
            elif spec.get("human_decision"):
                summary, evidence = run_human_resume(repository_root, output, spec)
            else:
                request = legacy._request_from_spec(repository_root, spec, base_goal)
                summary = run_request(repository_root, request, output)
                evidence = Path(summary["evidence_directory"])
            row["status"] = summary["status"]
            row["checks"] = assert_scenario(spec, summary, evidence)
            row["passed"] = True
            row["evidence_directory"] = str(evidence)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["traceback"] = traceback.format_exc()
        rows.append(row)

    known_limits = [
        row["scenario"]
        for row in rows
        if row["passed"] and row["expectation"] == "known-limit"
    ]
    result = {
        "schema": 3,
        "reference_contract": REFERENCE_CONTRACT,
        "output_directory": str(output),
        "passed": all(row["passed"] for row in rows),
        "known_limits_reproduced": known_limits,
        "scenarios": rows,
    }
    (output / "conformance-report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_matrix(
        args.repository_root.resolve(),
        args.output.resolve() if args.output else None,
    )
    for row in result["scenarios"]:
        label = (
            "KNOWN-LIMIT"
            if row["passed"] and row.get("expectation") == "known-limit"
            else ("PASS" if row["passed"] else "FAIL")
        )
        print(f"{row['scenario']:<32} {row.get('status','?'):<20} {label}")
        for check in row.get("checks", []):
            print(f"  - {check}")
        if not row["passed"]:
            print(f"  ! {row.get('error','unknown error')}")
    if result["passed"]:
        suffix = (
            f" | known limits reproduced: {', '.join(result['known_limits_reproduced'])}"
            if result["known_limits_reproduced"]
            else ""
        )
        print(f"\nConformance: PASS{suffix}")
    else:
        print("\nConformance: FAIL")
    print(f"Report: {Path(result['output_directory']) / 'conformance-report.json'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
