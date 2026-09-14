from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

from .engine import run_request
from .events import EventLog
from .scenarios import build_request, load_scenario, scenario_names
from .schema_validation import validate_evidence_directory


def _load_summary(evidence: Path) -> dict:
    return json.loads((evidence / "run-summary.json").read_text())


def assert_common(summary: dict, evidence: Path) -> list[str]:
    checks: list[str] = []
    seq, tip = EventLog.verify(evidence / "events.jsonl")
    if seq != summary["event_count"] or tip != summary["event_tip"]:
        raise AssertionError("event-chain consistency mismatch")
    checks.append("internal event-chain consistency")
    state = json.loads((evidence / "state.json").read_text())
    if state["status"] != summary["status"] or state["phase"] != summary["phase"]:
        raise AssertionError("durable state mismatch")
    checks.append("durable terminal state")
    validated = validate_evidence_directory(Path(__file__).resolve().parents[1], evidence)
    if not validated:
        raise AssertionError("no evidence artifacts were schema-validated")
    checks.append(f"schema validation ({len(validated)} artifacts)")
    return checks


def _assert_probe_blocks_despite_green_junit(evidence: Path) -> list[str]:
    diagnostic = json.loads((evidence / "test-candidate.json").read_text())
    probes = json.loads((evidence / "probe-candidate.json").read_text())
    review = json.loads((evidence / "review.json").read_text())
    if diagnostic["passed"] is not True:
        raise AssertionError("forgery fixture did not produce green diagnostic JUnit")
    if probes["all_passed"] is not False:
        raise AssertionError("controller probes were fooled by forged diagnostic evidence")
    if review["verdict"] != "block" or review["checks"]["controller_probes_green"] is not False:
        raise AssertionError("computed review did not block on controller probe failure")
    return ["diagnostic JUnit green but non-authoritative", "controller probes detect wrong behavior", "computed review blocks forgery"]


def assert_scenario(spec: dict, summary: dict, evidence: Path) -> list[str]:
    if summary["status"] != spec["expected_status"]:
        raise AssertionError(f"status {summary['status']} != {spec['expected_status']}")
    checks = ["expected terminal state"] + assert_common(summary, evidence)
    name = spec["name"]
    if name == "happy-path":
        review = json.loads((evidence / "review.json").read_text())
        candidate = json.loads((evidence / "candidate-evidence.json").read_text())
        probes = json.loads((evidence / "probe-candidate.json").read_text())
        negative = json.loads((evidence / "probe-negative-control.json").read_text())
        if review["verdict"] != "accept" or not all(review["checks"].values()):
            raise AssertionError("computed review did not accept happy path")
        if not probes["all_passed"] or not negative["negative_control_passed"]:
            raise AssertionError("controller probe or negative-control verification failed")
        if candidate["authority_snapshot_before"] != candidate["authority_snapshot_candidate"]:
            raise AssertionError("authority changed")
        if not summary["candidate_sha"] or not summary["merge_sha"] or summary["candidate_sha"] == summary["merge_sha"]:
            raise AssertionError("exact Git identities missing")
        checks += ["negative control", "controller-owned probe verification", "computed review", "exact candidate/merge identities"]
    elif name in {"forbidden-path", "test-tamper"}:
        decision = json.loads((evidence / "policy-decision.json").read_text())
        if decision["accepted"] is not False or summary["candidate_sha"] is not None:
            raise AssertionError("write boundary failed")
        checks += ["write-boundary rejection", "no candidate side effect"]
    elif name in {"budget-exceeded", "patch-budget-exceeded"}:
        if summary["candidate_sha"] is not None or "budget" not in summary.get("reason", ""):
            raise AssertionError("budget gate did not block before candidate")
        if name == "patch-budget-exceeded":
            proposal = json.loads((evidence / "proposal.json").read_text())
            if len(proposal["developer_edits"]) + len(proposal["tester_edits"]) > 4:
                raise AssertionError("patch-budget scenario also exceeded file-count budget")
            checks.append("patch-byte budget independently reachable")
        checks += ["pre-write budget gate", "no candidate side effect"]
    elif name == "risk-ceiling":
        if summary["candidate_sha"] is not None or "risk ceiling" not in summary.get("reason", ""):
            raise AssertionError("risk ceiling gate failed")
        checks += ["pre-write risk ceiling gate", "no candidate side effect"]
    elif name == "test-failure":
        diagnostic = json.loads((evidence / "test-candidate.json").read_text())
        probes = json.loads((evidence / "probe-candidate.json").read_text())
        if diagnostic["passed"] or probes["all_passed"] or summary["merge_sha"] is not None:
            raise AssertionError("failing implementation did not block merge")
        checks += ["diagnostic failure observed", "controller probe failure observed", "merge blocked"]
    elif name in {"insufficient-tests", "assertion-tamper", "junit-forgery"}:
        checks += _assert_probe_blocks_despite_green_junit(evidence)
        if name == "insufficient-tests":
            diagnostic = json.loads((evidence / "test-candidate.json").read_text())
            expected_names = {
                "test_acceptance_greet.GreetingAcceptanceTests.test_greet_reuses_normalization",
                "test_acceptance_greet.GreetingAcceptanceTests.test_greet_rejects_blank_name",
            }
            if not expected_names <= set(diagnostic["test_identities"]):
                raise AssertionError("empty-body fixture did not preserve expected test names")
            checks.append("correct test names with empty bodies cannot manufacture acceptance")
        elif name == "assertion-tamper":
            checks.append("candidate unittest monkeypatch cannot manufacture controller probe receipt")
        else:
            diagnostic = json.loads((evidence / "test-candidate.json").read_text())
            if diagnostic["tests"] != 5:
                raise AssertionError("JUnit forgery fixture did not manufacture five tests")
            checks.append("forged five-test JUnit cannot manufacture controller evidence")
    elif name == "human-gate":
        risk = json.loads((evidence / "risk-decision.json").read_text())
        if risk["risk"] != "high" or "HUMAN_GATE_THRESHOLD" not in risk["decision_reasons"] or summary["merge_sha"] is not None:
            raise AssertionError("high-risk human gate failed")
        checks += ["top-level critical path matched", "human gate"]
    elif name == "medium-auto-boundary":
        risk = json.loads((evidence / "risk-decision.json").read_text())
        if risk["risk"] != "medium" or "AUTO_MERGE_CEILING" not in risk["decision_reasons"]:
            raise AssertionError("medium auto-merge boundary failed")
        checks += ["medium risk reachable", "auto-merge ceiling independent"]
    elif name == "crash-recovery":
        recovery = json.loads((evidence / "recovery.json").read_text())
        merge = json.loads((evidence / "merge-evidence.json").read_text())
        if not recovery["process_resumed"] or not recovery["observed_existing_effect"] or merge["effect_occurrences"] != 1:
            raise AssertionError("process recovery or duplicate prevention failed")
        checks += ["actual process restart", "persisted pending effect", "single merge effect"]
    return checks


def run_crash_recovery(repository_root: Path, output: Path, spec: dict) -> tuple[dict, Path]:
    run_id = f"crash-recovery-{int(time.time()*1000)}"
    run_dir = output / run_id
    start = subprocess.run(
        [sys.executable, "-S", "-m", "reference_runtime.engine", "--repository-root", str(repository_root), "--output", str(output), "--scenario", spec["name"], "--run-id", run_id],
        cwd=repository_root, text=True, capture_output=True,
    )
    if start.returncode != 75:
        raise AssertionError(f"crash fixture did not terminate at injected crash: rc={start.returncode}\n{start.stdout}\n{start.stderr}")
    state = json.loads((run_dir / "evidence" / "state.json").read_text())
    if state["phase"] != "MERGE_PENDING" or not state["pending_effect"]:
        raise AssertionError("pending effect was not durable at crash boundary")
    first = subprocess.run(
        [sys.executable, "-S", "-m", "reference_runtime.engine", "--repository-root", str(repository_root), "--resume", str(run_dir)],
        cwd=repository_root, text=True, capture_output=True,
    )
    if first.returncode:
        raise AssertionError(f"resume process failed: {first.stderr}")
    summary = _load_summary(run_dir / "evidence")
    merge_sha = summary["merge_sha"]
    second = subprocess.run(
        [sys.executable, "-S", "-m", "reference_runtime.engine", "--repository-root", str(repository_root), "--resume", str(run_dir)],
        cwd=repository_root, text=True, capture_output=True,
    )
    if second.returncode:
        raise AssertionError(f"second resume failed: {second.stderr}")
    if _load_summary(run_dir / "evidence")["merge_sha"] != merge_sha:
        raise AssertionError("second resume changed merge identity")
    return summary, run_dir / "evidence"


def run_matrix(repository_root: Path, output: Path | None = None) -> dict:
    if output is None:
        output = repository_root / ".demo" / "conformance" / time.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=True)
    base_goal = json.loads((repository_root / "examples" / "goal.example.json").read_text())
    rows: list[dict] = []
    for name in scenario_names(repository_root):
        spec = load_scenario(repository_root, name)
        row = {"scenario": name, "expected_status": spec["expected_status"], "passed": False, "checks": []}
        try:
            if spec.get("fault_injection"):
                summary, evidence = run_crash_recovery(repository_root, output, spec)
            else:
                request = build_request(repository_root, name, base_goal)
                summary = run_request(repository_root, request, output)
                evidence = Path(summary["evidence_directory"])
            row["status"] = summary["status"]
            row["evidence_directory"] = str(evidence)
            row["checks"] = assert_scenario(spec, summary, evidence)
            row["passed"] = True
        except Exception as exc:
            row["status"] = row.get("status", "HARNESS_ERROR")
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["traceback"] = traceback.format_exc()
        rows.append(row)
    result = {
        "schema": 2,
        "reference_contract": "gitops-agent-control-plane/v4",
        "output_directory": str(output),
        "passed": all(row["passed"] for row in rows),
        "scenarios": rows,
    }
    (output / "conformance-report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the standalone reference conformance matrix.")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_matrix(args.repository_root.resolve(), args.output.resolve() if args.output else None)
    for row in result["scenarios"]:
        print(f"{row['scenario']:<24} {row.get('status','?'):<20} {'PASS' if row['passed'] else 'FAIL'}")
        for check in row.get("checks", []):
            print(f"  - {check}")
        if not row["passed"]:
            print(f"  ! {row.get('error','unknown error')}")
            print(f"  ! evidence/report retained under {result['output_directory']}")
    print(f"\nConformance: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"Report: {Path(result['output_directory']) / 'conformance-report.json'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
