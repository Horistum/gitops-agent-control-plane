#!/usr/bin/env python3
"""Compare actual reference/Flow lifecycle decisions using real Git and processes.

Both reasoning peers and GitHub service observations are controlled test peers.
This is an executable adapter contract, not authenticated Codex or Kotlin evidence.
Run against a trusted Flow checkout containing its full tests and locked core.
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def worker(profile, consumer):
    root = ROOT if profile == "reference" else consumer
    sys.path[:0] = [str(root), str(root / "tests")]
    import control_plane_core.workflow as domain
    transitions = []
    def observe(frame, event, value):
        if event == "return" and frame.f_code is domain.workflow_transition.__code__ and isinstance(value, dict):
            if frame.f_locals["event"]["kind"] in {"advance", "verification"}:
                transitions.append([frame.f_locals["state"]["phase"], value["phase"]])
    with contextlib.redirect_stdout(io.StringIO()):
        if profile == "reference":
            from agent_runtime.controller import Controller
            from runtime_support import build_product, policy, goal, InProcessProvider
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory); build_product(path / "product")
                configuration = policy(path / "product"); configuration["challenge"] = False
                engine = Controller.start(path / "run", configuration, goal(), trusted_local=True)
                engine.reasoning = InProcessProvider()
                sys.setprofile(observe)
                try:
                    for _ in range(80):
                        status = engine.tick()
                        if status["status"] != "RUNNING": break
                finally:
                    sys.setprofile(None)
                if status["status"] != "COMPLETED": raise AssertionError(status)
                task = engine.state["archive"][0]
                negative, merged = task["independent_baseline"], task["postmerge_evidence"]
        else:
            from test_verified_git_loop import VerifiedGitLoopTests
            # Uses the exact production facade, including durable context/recovery.
            from flow_loop.runtime import Controller
            fixture = VerifiedGitLoopTests(); fixture.setUp()
            try:
                fixture.c = Controller(fixture.store, fixture.p, fixture.product, fixture.gh,
                    fixture.a, fixture.tests, fixture.root / "spool", clock=lambda: 1700000100)
                sys.setprofile(observe)
                try:
                    task = fixture.until("done")
                finally:
                    sys.setprofile(None)
                negative, merged = task["counterfactual_receipt"], task["postmerge_machine"]
            finally:
                fixture.doCleanups()
    if negative["passed"] is not False or merged["passed"] is not True:
        raise AssertionError("Missing actual counterfactual/merge execution")
    return {"profile": profile, "transitions": transitions,
            "negative_control_executed": True, "merged_product_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument("--worker", choices=("reference", "flow"))
    args = parser.parse_args(); consumer = args.consumer.resolve()
    if args.worker:
        print(json.dumps(worker(args.worker, consumer))); return
    from sync_control_core import check, inventory
    check(consumer)
    if inventory(ROOT) != inventory(consumer):
        raise SystemExit("Adapter comparison requires identical reviewed core bytes")
    profiles = []
    for profile in ("reference", "flow"):
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()),
            "--consumer", str(consumer), "--worker", profile], capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise SystemExit(result.stderr[-6000:])
        profiles.append(json.loads(result.stdout))
    if profiles[0]["transitions"] != profiles[1]["transitions"]:
        raise SystemExit("Adapter phase drift: " + json.dumps(profiles))
    print(json.dumps({"schema": 1, "passed": True, "scope": "actual-adapter-workflow-parity",
                      "live_providers": False, "profiles": profiles}, indent=2))


if __name__ == "__main__": main()
