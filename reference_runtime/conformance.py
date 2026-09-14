from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import traceback

from . import _conformance_impl as base
from .contracts import REFERENCE_CONTRACT
from .engine import run_request
from .scenarios import load_scenario, scenario_names


def run_crash_recovery(repository_root: Path, output: Path, spec: dict) -> tuple[dict, Path]:
    if spec.get("fault_injection") != "after-release-state-effect-before-receipt":
        return base.run_crash_recovery(repository_root, output, spec)

    run_id = f"release-state-crash-recovery-{int(time.time()*1000)}"
    run_dir = output / run_id
    start = base._run_subprocess([
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
    if start.returncode != 75:
        raise AssertionError(
            f"control-state crash fixture did not terminate at injected crash: rc={start.returncode}\n{start.stdout}\n{start.stderr}"
        )
    state = json.loads((run_dir / "evidence" / "state.json").read_text())
    pending = state.get("pending_effect")
    if state.get("phase") != "CONTROL_STATE_PENDING" or not isinstance(pending, dict) or pending.get("effect") != "control-state":
        raise AssertionError("pending control-state effect was not durable at crash boundary")
    resumed = base._run_subprocess([
        sys.executable,
        "-S",
        "-m",
        "reference_runtime.engine",
        "--repository-root",
        str(repository_root),
        "--resume",
        str(run_dir),
    ], repository_root)
    if resumed.returncode:
        raise AssertionError(f"control-state resume process failed: {resumed.stderr}")
    return base._load_summary(run_dir / "evidence"), run_dir / "evidence"


def assert_scenario(spec: dict, summary: dict, evidence: Path) -> list[str]:
    checks = base.assert_scenario(spec, summary, evidence)
    if spec["name"] != "release-state-crash-recovery":
        return checks

    if summary.get("status") != "COMPLETED" or summary.get("goal_status") != "SATISFIED":
        raise AssertionError("control-state recovery did not continue through goal reconciliation")
    if "EXAMPLE-001" not in summary.get("completed_items", []):
        raise AssertionError("recovered control-state effect did not record completed item")
    recovery = json.loads((evidence / "control-state-recovery.json").read_text())
    if (
        recovery.get("process_resumed") is not True
        or recovery.get("effect") != "control-state"
        or recovery.get("observed_existing_effect") is not True
        or recovery.get("duplicate_effect_prevented") is not True
        or recovery.get("effect_occurrences_before_resume") != 1
    ):
        raise AssertionError("control-state effect recovery did not observe and reuse the existing Git effect")
    state = json.loads((evidence / "state.json").read_text())
    if state.get("pending_effect") is not None:
        raise AssertionError("control-state pending effect was not consumed after recovery")
    if not (evidence / "control-state-intent.json").is_file():
        raise AssertionError("control-state durable intent evidence missing")
    if not (evidence / "release-transition-example-001.json").is_file():
        raise AssertionError("release transition evidence missing after control-state recovery")
    checks += [
        "release-state effect intent persisted before Git side effect",
        "actual process restart after control-state Git commit",
        "existing Control-State-Id effect reused exactly once",
        "recovered release-state transition reconciled the goal",
    ]
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
                summary, evidence = run_crash_recovery(repository_root, output, spec)
            elif spec.get("human_decision"):
                summary, evidence = base.run_human_resume(repository_root, output, spec)
            else:
                request = base._request_from_spec(repository_root, spec, base_goal)
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
        print(f"{row['scenario']:<30} {row.get('status','?'):<20} {label}")
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
