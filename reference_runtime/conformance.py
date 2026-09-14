from __future__ import annotations

from copy import deepcopy
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

from .contracts import REFERENCE_CONTRACT
from .engine import run_request
from .events import EventLog
from .scenarios import developer_proposal, load_scenario, scenario_names, tester_proposal
from .schema_validation import validate_evidence_directory


def _load_summary(evidence: Path) -> dict:
    return json.loads((evidence / "run-summary.json").read_text())


def _request_from_spec(repository_root: Path, spec: dict, base_goal: dict) -> dict:
    goal = deepcopy(base_goal)
    if spec.get("goal_items"):
        goal["items"] = list(spec["goal_items"])
    else:
        goal["items"] = ["EXAMPLE-001"]
    goal["success_condition"] = "Every requested item is controller-recorded complete after exact post-merge verification."
    for key, value in spec.get("goal_overrides", {}).items():
        if key in {"risk_ceiling", "auto_merge_ceiling"}:
            goal[key] = value
        elif key in {"max_cycles", "max_attempts_per_item"}:
            goal["autonomy"][key] = value
        else:
            raise ValueError(f"unsupported goal override: {key}")

    catalog: dict[str, list[dict]] = {}
    if spec.get("work"):
        for item_id, attempts in spec["work"].items():
            catalog[item_id] = [
                {
                    "developer_proposal": developer_proposal(row["developer_fixture"], item_id),
                    "tester_proposal": tester_proposal(row["tester_fixture"], item_id),
                }
                for row in attempts
            ]
    else:
        catalog["EXAMPLE-001"] = [
            {
                "developer_proposal": developer_proposal(spec["developer_fixture"], "EXAMPLE-001"),
                "tester_proposal": tester_proposal(spec["tester_fixture"], "EXAMPLE-001"),
            }
        ]
    return {
        "schema": 2,
        "label": spec["name"],
        "proposal_source": "trusted-fixture",
        "goal": goal,
        "work_catalog": catalog,
        "fault_injection": spec.get("fault_injection"),
    }


def assert_common(summary: dict, evidence: Path) -> list[str]:
    checks: list[str] = []
    seq, tip = EventLog.verify(evidence / "events.jsonl")
    if seq != summary["event_count"] or tip != summary["event_tip"]:
        raise AssertionError("event-chain consistency mismatch")
    checks.append("internal event-chain consistency")
    state = json.loads((evidence / "state.json").read_text())
    if state["status"] != summary["status"] or state["phase"] != summary["phase"]:
        raise AssertionError("durable state mismatch")
    if state.get("goal_status") != summary.get("goal_status"):
        raise AssertionError("goal status mismatch")
    checks.append("durable terminal/pause state")
    validated = validate_evidence_directory(Path(__file__).resolve().parents[1], evidence)
    if not validated:
        raise AssertionError("no evidence artifacts were schema-validated")
    checks.append(f"schema validation ({len(validated)} artifacts)")
    return checks


def _assert_signed_receipts(probes: dict) -> None:
    for row in probes["probes"]:
        receipt = row.get("receipt")
        if row.get("receipt_count") != 1 or row.get("receipt_valid") is not True:
            raise AssertionError(f"probe {row.get('probe_id')} does not have exactly one valid signed receipt")
        if not isinstance(receipt, dict) or receipt.get("protocol") != 3:
            raise AssertionError(f"probe {row.get('probe_id')} receipt protocol mismatch")


def _assert_probe_blocks_despite_green_junit(evidence: Path) -> list[str]:
    diagnostic = json.loads((evidence / "test-candidate.json").read_text())
    probes = json.loads((evidence / "probe-candidate.json").read_text())
    review = json.loads((evidence / "review.json").read_text())
    if diagnostic["passed"] is not True:
        raise AssertionError("forgery fixture did not produce green diagnostic JUnit")
    if probes["all_passed"] is not False:
        raise AssertionError("controller probes were fooled by forged diagnostic evidence")
    _assert_signed_receipts(probes)
    if review["verdict"] != "block" or review["checks"]["controller_probes_green"] is not False:
        raise AssertionError("computed review did not block on controller probe failure")
    return [
        "diagnostic JUnit green but non-authoritative",
        "controller probes detect wrong behavior",
        "exactly one HMAC-authenticated parent receipt per probe",
        "computed review blocks forgery",
    ]


def _workspace_greet(workspace: Path, value: str) -> str:
    service = workspace / "src" / "reference_app" / "service.py"
    script = (
        "import importlib.util;"
        f"p={str(service)!r};"
        "s=importlib.util.spec_from_file_location('_known_limit_service',p);"
        "m=importlib.util.module_from_spec(s);"
        "s.loader.exec_module(m);"
        f"print(m.greet({value!r}))"
    )
    result = subprocess.run([sys.executable, "-S", "-c", script], cwd=workspace, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(f"direct candidate behavior check failed: {result.stderr}")
    return result.stdout.strip()


def _event_types(evidence: Path) -> list[str]:
    return [json.loads(line)["type"] for line in (evidence / "events.jsonl").read_text().splitlines()]


def assert_scenario(spec: dict, summary: dict, evidence: Path) -> list[str]:
    if summary["status"] != spec["expected_status"]:
        raise AssertionError(f"status {summary['status']} != {spec['expected_status']}")
    checks = ["expected terminal/pause state"] + assert_common(summary, evidence)
    name = spec["name"]
    workspace = evidence.parent / "workspace"

    if name in {"happy-path", "autonomous-two-item", "repair-loop", "human-approve-resume"}:
        if summary.get("goal_status") != "SATISFIED" or summary.get("goal_satisfied") is not True:
            raise AssertionError("successful autonomous run did not satisfy the requested goal")
        evaluation = json.loads((evidence / "goal-evaluation.json").read_text())
        if evaluation["satisfied"] is not True:
            raise AssertionError("final goal reconciliation is not satisfied")
        control = json.loads((evidence / "control-loop.json").read_text())
        if control["goal_satisfied"] is not True:
            raise AssertionError("control-loop evidence did not record goal satisfaction")
        checks += ["goal reconciliation satisfied", "control-loop evidence recorded"]

    if name == "happy-path":
        review = json.loads((evidence / "review.json").read_text())
        probes = json.loads((evidence / "probe-candidate.json").read_text())
        negative = json.loads((evidence / "probe-negative-control.json").read_text())
        if review["verdict"] != "accept" or not probes["all_passed"] or not negative["negative_control_passed"]:
            raise AssertionError("happy path verification/review failed")
        if negative.get("negative_control_all_cases_rejected") is not True:
            raise AssertionError("negative control did not reject every acceptance case")
        _assert_signed_receipts(probes)
        if "EXAMPLE-001" not in summary["completed_items"]:
            raise AssertionError("release-state did not record completed item")
        if not (evidence / "release-transition-example-001.json").is_file():
            raise AssertionError("controller release-state transition evidence missing")
        checks += ["case-level negative control", "signed exact-revision probes", "controller-owned release-state transition"]

    elif name == "autonomous-two-item":
        if summary["completed_items"] != ["EXAMPLE-001", "EXAMPLE-002"]:
            raise AssertionError(f"unexpected completed item order: {summary['completed_items']}")
        control = json.loads((evidence / "control-loop.json").read_text())
        if [row["item"] for row in control["cycles"]] != ["EXAMPLE-001", "EXAMPLE-002"]:
            raise AssertionError("controller did not select dependency-ordered two-item work")
        if not all(row["result"] == "COMPLETED" for row in control["cycles"]):
            raise AssertionError("not all autonomous cycles completed")
        for item in ("example-001", "example-002"):
            if not (evidence / f"release-transition-{item}.json").is_file():
                raise AssertionError(f"release transition missing for {item}")
        checks += [
            "dependency-ready item selection",
            "two controller-owned release-state transitions",
            "completed-item acceptance promoted to regression verification",
            "objective terminates only after both items complete",
        ]

    elif name == "repair-loop":
        control = json.loads((evidence / "control-loop.json").read_text())
        attempts = control["cycles"][0]["attempts"]
        if len(attempts) != 2 or attempts[0]["result"] != "REPAIR_REQUESTED" or attempts[1]["result"] != "COMPLETED":
            raise AssertionError(f"repair loop did not execute failed->repair->success: {attempts}")
        if not (evidence / "feedback-example-001-attempt-01.json").is_file():
            raise AssertionError("repair feedback artifact missing")
        checks += ["verification feedback routed to repair", "bounded second attempt succeeded"]

    elif name == "dependency-blocked":
        if summary.get("goal_status") != "AUTHORITY_EXHAUSTED" or summary.get("candidate_sha") is not None:
            raise AssertionError("dependency dead-end did not fail before candidate work")
        evaluation = json.loads((evidence / "goal-evaluation.json").read_text())
        if evaluation["blocked_dependencies"].get("EXAMPLE-002") != ["EXAMPLE-001"]:
            raise AssertionError("blocked dependency was not explained")
        checks += ["dependency dead-end fail-closed", "no invented out-of-authority work"]

    elif name in {"human-approve-resume", "human-reject-resume", "human-request-changes"}:
        decision = spec["human_decision"]
        archive = evidence / "human-decision-example-001-attempt-01.json"
        if not archive.is_file():
            raise AssertionError("human decision archive missing")
        human = json.loads(archive.read_text())
        if human["decision"] != decision or human["decided_by"] != "conformance-human":
            raise AssertionError("human decision evidence mismatch")
        if "human-decision-recorded" not in _event_types(evidence):
            raise AssertionError("human decision event missing")
        checks += ["human authority decision persisted", "fresh-process resume path exercised"]
        if name == "human-approve-resume":
            if summary["status"] != "COMPLETED" or summary["merge_sha"] is None:
                raise AssertionError("human approval did not continue to verified merge")
            checks.append("human approval resumed merge/reconciliation")
        elif name == "human-reject-resume":
            if summary["status"] != "BLOCKED_POLICY" or summary["merge_sha"] is not None:
                raise AssertionError("human rejection did not block merge")
            checks.append("human rejection blocked effect")
        else:
            if summary["status"] != "NEEDS_DECISION" or summary["attempt"] != 2:
                raise AssertionError("request_changes did not route to bounded second attempt/human boundary")
            if not (evidence / "feedback-example-001-attempt-01.json").is_file():
                raise AssertionError("human request-changes feedback missing")
            checks.append("human request_changes routed into bounded repair/replan")

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
        if not (evidence / "feedback-example-001-attempt-01.json").is_file():
            raise AssertionError("verification failure did not produce feedback")
        checks += ["diagnostic failure observed", "controller probe failure observed", "bounded feedback emitted", "merge blocked"]

    elif name in {"insufficient-tests", "assertion-tamper", "junit-forgery", "receipt-injection", "probe-aware"}:
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
        elif name == "junit-forgery":
            diagnostic = json.loads((evidence / "test-candidate.json").read_text())
            if diagnostic["tests"] != 5:
                raise AssertionError("JUnit forgery fixture did not manufacture five tests")
            checks.append("forged five-test JUnit cannot manufacture controller evidence")
        elif name == "receipt-injection":
            probes = json.loads((evidence / "probe-candidate.json").read_text())
            injection_count = sum(
                case.get("candidate_receipt_injection_count", 0)
                for row in probes["probes"]
                if isinstance(row.get("receipt"), dict)
                for case in row["receipt"].get("cases", [])
            )
            if injection_count < 1:
                raise AssertionError("receipt-injection fixture never exercised its attack path")
            checks += ["current-protocol receipt injection actually executed", "candidate child stdout cannot inject parent receipt"]
        else:
            probes = json.loads((evidence / "probe-candidate.json").read_text())
            unicode_row = next((row for row in probes["probes"] if row["probe_id"] == "greet-unicode"), None)
            if not unicode_row or not isinstance(unicode_row.get("receipt"), dict):
                raise AssertionError("probe-aware scenario did not execute greet-unicode")
            if not all(case.get("passed") is False for case in unicode_row["receipt"].get("cases", [])):
                raise AssertionError("narrow overfit unexpectedly satisfied unicode invariant")
            checks += ["current narrow overfit fails unicode invariant", "generic DSL oracle exercised"]

    elif name == "raw-outcome-forgery":
        if spec.get("expectation") != "known-limit":
            raise AssertionError("raw-outcome forgery must be known-limit")
        diagnostic = json.loads((evidence / "test-candidate.json").read_text())
        probes = json.loads((evidence / "probe-candidate.json").read_text())
        review = json.loads((evidence / "review.json").read_text())
        if diagnostic["passed"] is not True or probes["all_passed"] is not True or review["verdict"] != "accept":
            raise AssertionError("known raw-outcome limit was not reproduced through authorization")
        _assert_signed_receipts(probes)
        cases = [
            case
            for row in probes["probes"]
            if isinstance(row.get("receipt"), dict)
            for case in row["receipt"].get("cases", [])
        ]
        if not cases or not all(isinstance(c.get("outcome"), dict) and c["outcome"].get("candidate_forged") is True for c in cases):
            raise AssertionError("not every raw observation was candidate-forged")
        observed = _workspace_greet(workspace, "Žluťoučký Ω")
        if observed == "Hello, Žluťoučký Ω!":
            raise AssertionError("known-limit candidate unexpectedly implements protected behavior")
        checks += ["KNOWN LIMIT reproduced: candidate forged current raw-outcome channel", "parent signed candidate-forged observations", "direct behavior remains wrong despite accepted probes"]

    elif name in {"human-gate", "medium-auto-boundary"}:
        risk = json.loads((evidence / "risk-decision.json").read_text())
        if summary["status"] != "NEEDS_DECISION" or summary["merge_sha"] is not None:
            raise AssertionError("human/auto authority boundary did not pause")
        if name == "human-gate" and (risk["risk"] != "high" or "HUMAN_GATE_THRESHOLD" not in risk["decision_reasons"]):
            raise AssertionError("high-risk human gate failed")
        if name == "medium-auto-boundary" and (risk["risk"] != "medium" or "AUTO_MERGE_CEILING" not in risk["decision_reasons"]):
            raise AssertionError("medium auto-merge boundary failed")
        checks += ["durable NEEDS_DECISION authority boundary", "no merge before human authority"]

    elif name == "crash-recovery":
        recovery = json.loads((evidence / "recovery.json").read_text())
        merge = json.loads((evidence / "merge-evidence.json").read_text())
        if not recovery["process_resumed"] or not recovery["observed_existing_effect"] or merge["effect_occurrences"] != 1:
            raise AssertionError("process recovery or duplicate prevention failed")
        if summary.get("goal_status") != "SATISFIED":
            raise AssertionError("recovered run did not continue through reconciliation")
        checks += ["actual process restart", "persisted pending effect", "single merge effect", "recovered run reconciled goal"]

    return checks


def _run_subprocess(argv: list[str], repository_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=repository_root, text=True, capture_output=True)


def run_crash_recovery(repository_root: Path, output: Path, spec: dict) -> tuple[dict, Path]:
    run_id = f"crash-recovery-{int(time.time()*1000)}"
    run_dir = output / run_id
    start = _run_subprocess([sys.executable, "-S", "-m", "reference_runtime.engine", "--repository-root", str(repository_root), "--output", str(output), "--scenario", spec["name"], "--run-id", run_id], repository_root)
    if start.returncode != 75:
        raise AssertionError(f"crash fixture did not terminate at injected crash: rc={start.returncode}\n{start.stdout}\n{start.stderr}")
    state = json.loads((run_dir / "evidence" / "state.json").read_text())
    if state["phase"] != "MERGE_PENDING" or not state["pending_effect"]:
        raise AssertionError("pending merge effect was not durable at crash boundary")
    resumed = _run_subprocess([sys.executable, "-S", "-m", "reference_runtime.engine", "--repository-root", str(repository_root), "--resume", str(run_dir)], repository_root)
    if resumed.returncode:
        raise AssertionError(f"resume process failed: {resumed.stderr}")
    return _load_summary(run_dir / "evidence"), run_dir / "evidence"


def run_human_resume(repository_root: Path, output: Path, spec: dict) -> tuple[dict, Path]:
    run_id = f"{spec['name']}-{int(time.time()*1000)}"
    run_dir = output / run_id
    start = _run_subprocess([sys.executable, "-S", "-m", "reference_runtime.engine", "--repository-root", str(repository_root), "--output", str(output), "--scenario", spec["name"], "--run-id", run_id], repository_root)
    if start.returncode:
        raise AssertionError(f"human-gate start process failed: {start.stderr}")
    initial = _load_summary(run_dir / "evidence")
    if initial["status"] != "NEEDS_DECISION":
        raise AssertionError(f"human scenario did not pause first: {initial['status']}")
    resumed = _run_subprocess([
        sys.executable, "-S", "-m", "reference_runtime.engine", "--repository-root", str(repository_root),
        "--resume", str(run_dir), "--decision", spec["human_decision"], "--decided-by", "conformance-human",
    ], repository_root)
    if resumed.returncode:
        raise AssertionError(f"human resume process failed: {resumed.stderr}")
    return _load_summary(run_dir / "evidence"), run_dir / "evidence"


def run_matrix(repository_root: Path, output: Path | None = None) -> dict:
    if output is None:
        output = repository_root / ".demo" / "conformance" / time.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=True)
    base_goal = json.loads((repository_root / "examples" / "goal.example.json").read_text())
    rows: list[dict] = []
    for name in scenario_names(repository_root):
        spec = load_scenario(repository_root, name)
        row = {"scenario": name, "expected_status": spec["expected_status"], "expectation": spec.get("expectation", "enforced"), "passed": False, "checks": []}
        try:
            if spec.get("fault_injection"):
                summary, evidence = run_crash_recovery(repository_root, output, spec)
            elif spec.get("human_decision"):
                summary, evidence = run_human_resume(repository_root, output, spec)
            else:
                request = _request_from_spec(repository_root, spec, base_goal)
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
    known_limits = [row["scenario"] for row in rows if row["passed"] and row["expectation"] == "known-limit"]
    result = {
        "schema": 3,
        "reference_contract": REFERENCE_CONTRACT,
        "output_directory": str(output),
        "passed": all(row["passed"] for row in rows),
        "known_limits_reproduced": known_limits,
        "scenarios": rows,
    }
    (output / "conformance-report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_matrix(args.repository_root.resolve(), args.output.resolve() if args.output else None)
    for row in result["scenarios"]:
        label = "KNOWN-LIMIT" if row["passed"] and row.get("expectation") == "known-limit" else ("PASS" if row["passed"] else "FAIL")
        print(f"{row['scenario']:<24} {row.get('status','?'):<20} {label}")
        for check in row.get("checks", []):
            print(f"  - {check}")
        if not row["passed"]:
            print(f"  ! {row.get('error','unknown error')}")
    if result["passed"]:
        suffix = f" | known limits reproduced: {', '.join(result['known_limits_reproduced'])}" if result["known_limits_reproduced"] else ""
        print(f"\nConformance: PASS{suffix}")
    else:
        print("\nConformance: FAIL")
    print(f"Report: {Path(result['output_directory']) / 'conformance-report.json'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
