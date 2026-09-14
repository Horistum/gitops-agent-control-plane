from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from .engine import run_one
from .events import EventLog
from .scenarios import EXPECTED_OUTCOME, SUPPORTED


def assert_scenario(summary: dict, evidence: Path) -> list[str]:
    checks: list[str] = []
    scenario = summary["scenario"]

    if summary["status"] != EXPECTED_OUTCOME[scenario]:
        raise AssertionError(f"{scenario}: status {summary['status']} != {EXPECTED_OUTCOME[scenario]}")
    checks.append("expected terminal state")

    seq, tip = EventLog.verify(evidence / "events.jsonl")
    if seq != summary["event_count"] or tip != summary["event_tip"]:
        raise AssertionError(f"{scenario}: event-chain mismatch")
    checks.append("hash-linked event chain")

    state = json.loads((evidence / "state.json").read_text())
    if state["status"] != summary["status"]:
        raise AssertionError(f"{scenario}: durable state mismatch")
    checks.append("durable state")

    if scenario == "happy-path":
        for name in ("candidate-evidence.json", "review.json", "merge-evidence.json", "postmerge-evidence.json"):
            if not (evidence / name).is_file():
                raise AssertionError(f"{scenario}: missing {name}")
        if not summary["candidate_sha"] or not summary["merge_sha"] or summary["candidate_sha"] == summary["merge_sha"]:
            raise AssertionError(f"{scenario}: exact Git identities missing")
        if summary["candidate_tests"] < 5 or summary["postmerge_tests"] < 5:
            raise AssertionError(f"{scenario}: executable acceptance tests missing")
        checks += ["exact candidate/merge identities", "candidate/post-merge verification"]

    elif scenario == "forbidden-path":
        decision = json.loads((evidence / "policy-decision.json").read_text())
        if decision["accepted"] is not False:
            raise AssertionError("forbidden-path: unauthorized proposal was accepted")
        if summary["candidate_sha"] is not None or summary["merge_sha"] is not None:
            raise AssertionError("forbidden-path: candidate/merge should not exist")
        checks += ["write-boundary rejection", "no candidate side effect"]

    elif scenario == "test-failure":
        candidate = json.loads((evidence / "test-candidate.json").read_text())
        if candidate["passed"] is not False or summary["merge_sha"] is not None:
            raise AssertionError("test-failure: failed verification did not block merge")
        checks += ["real test failure observed", "merge blocked"]

    elif scenario == "human-gate":
        decision = json.loads((evidence / "human-decision.json").read_text())
        risk = json.loads((evidence / "risk-decision.json").read_text())
        if decision["required"] is not True or risk["risk"] != "high" or summary["merge_sha"] is not None:
            raise AssertionError("human-gate: critical-path escalation failed")
        checks += ["critical-path escalation", "human decision required"]

    elif scenario == "crash-recovery":
        recovery = json.loads((evidence / "recovery.json").read_text())
        if not recovery["recovered_pending_effect"] or not recovery["duplicate_effect_prevented"]:
            raise AssertionError("crash-recovery: pending effect recovery failed")
        if not summary["merge_sha"]:
            raise AssertionError("crash-recovery: recovered run did not complete")
        checks += ["pending-effect recovery", "duplicate effect prevention"]

    return checks


def run_matrix(repository_root: Path, output: Path | None = None) -> dict:
    owned_tmp = None
    if output is None:
        owned_tmp = tempfile.TemporaryDirectory(prefix="agent-control-conformance-")
        output = Path(owned_tmp.name)
    output.mkdir(parents=True, exist_ok=True)

    rows = []
    try:
        for scenario in SUPPORTED:
            summary = run_one(repository_root, scenario, output)
            evidence = Path(summary["evidence_directory"])
            checks = assert_scenario(summary, evidence)
            rows.append(
                {
                    "scenario": scenario,
                    "status": summary["status"],
                    "checks": checks,
                    "passed": True,
                }
            )
        return {
            "schema": 1,
            "reference_contract": "gitops-agent-control-plane/v2",
            "passed": all(row["passed"] for row in rows),
            "scenarios": rows,
        }
    finally:
        if owned_tmp is not None:
            owned_tmp.cleanup()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the standalone reference conformance matrix.")
    p.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    result = run_matrix(a.repository_root.resolve(), a.output.resolve() if a.output else None)
    for row in result["scenarios"]:
        print(f"{row['scenario']:<18} {row['status']:<20} PASS")
        for check in row["checks"]:
            print(f"  - {check}")
    print(f"\nConformance: {'PASS' if result['passed'] else 'FAIL'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
