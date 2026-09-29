#!/usr/bin/env python3
"""Compare actual reference/Flow safety behavior with real Git and fixture processes.

Run from either checkout with --reference PATH --consumer PATH. Reasoning and
GitHub observations are controlled peers; no live provider or product claim is
made. Both trusted checkouts must contain their full test fixtures and same core.
"""
import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("full-route", "adaptive-low-route", "negative-control-repair",
             "stale-review-evidence", "working-set-authority", "model-receipt-replay",
             "uncertain-model-fence", "ci-newer-pending", "ci-conflicting", "ci-malformed",
             "ci-cancelled", "ci-latest-failure", "separate-work-merge-approval")


def ci_rows(name):
    def row(identity, conclusion="failure", status="completed"):
        return {"id": identity, "name": "build", "app_id": 15368,
                "status": status, "conclusion": conclusion}
    return {"ci-newer-pending": [row(1), row(2, None, "in_progress")],
            "ci-conflicting": [row(1), row(1, "success")],
            "ci-malformed": [row(1), row(2, None)],
            "ci-cancelled": [row(1), row(2, "cancelled")],
            "ci-latest-failure": [row(1, "success"), row(2)]}[name]


def ci_outcome(name, phase, repairs, calls_before, calls_after):
    expected = "developer" if name == "ci-latest-failure" else (
        "await_human" if name in {"ci-conflicting", "ci-malformed"} else "ci")
    require(phase == expected, "CI observation routed to " + phase + "; expected " + expected)
    require(repairs == int(name == "ci-latest-failure"), "CI observation consumed wrong repair budget")
    require(calls_before == calls_after, "CI observation dispatched a model")
    return {"phase": phase, "repairs": repairs, "model_calls": 0, "merged": False}


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


class Interrupted(BaseException):
    """Hard interruption which bypasses an adapter's ordinary error handling."""


@contextlib.contextmanager
def trace_workflow():
    import control_plane_core.workflow as domain
    rows = []
    previous = sys.getprofile()

    def observe(frame, event, value):
        if event == "return" and frame.f_code is domain.workflow_transition.__code__ and isinstance(value, dict):
            supplied = frame.f_locals["event"]
            # Adapters may recheck unchanged risk; compare actual decisions.
            if supplied["kind"] != "risk" or value["phase"] != frame.f_locals["state"]["phase"]:
                rows.append({"from": frame.f_locals["state"]["phase"], "to": value["phase"],
                             "invalidated": value["invalidated"]})

    sys.setprofile(observe)
    try:
        yield rows
    finally:
        sys.setprofile(previous)


def delivery(task, negative, merged):
    require(negative["passed"] is False, "New-behavior test must actually fail on base")
    require(merged["passed"] is True, "Merged product must actually pass")
    require(merged["head"] == task["merge_sha"], "Merged observation has another head")
    require(all(merged[k] == task[k] for k in ("base", "spec_hash")), "Stale postmerge identity")
    return {"completed": True, "negative_control_executed": True,
            "merged_product_verified": True, "postmerge_identity_exact": True}


def reference_scenario(name):
    from agent_runtime.controller import Controller
    from runtime_support import build_product, policy, goal, InProcessProvider
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        build_product(root / "product")
        configuration = policy(root / "product")
        configuration.update(challenge=False, adaptive_agent_graph=name == "adaptive-low-route")

        def transform(payload, value, _):
            if name == "separate-work-merge-approval" and payload["phase"] == "architect":
                value["risk"] = "high"
            if name == "negative-control-repair" and payload["phase"] == "tester" and payload["task"]["repairs"] == 0:
                value["edits"][0]["content"] = value["edits"][0]["content"].replace(
                    "self.assertEqual(value(), 2)", "self.assertGreater(value(), 0)")
            if name == "working-set-authority" and payload["phase"] == "developer":
                value["edits"].append({"path": "other.py", "expected_sha256": "", "delete": False,
                                       "content": "# outside the approved working set\n"})

        provider = InProcessProvider(transform)
        engine = Controller.start(root / "run", configuration, goal(), trusted_local=True)
        engine.reasoning = provider

        def drive(phase=None):
            for _ in range(160):
                status = engine.tick()
                if status["status"] != "RUNNING" or status["phase"] == phase:
                    return status
            raise AssertionError("Reference fixture did not converge")

        if name == "uncertain-model-fence":
            def interrupt(*_):
                raise Interrupted()
            provider.transform = interrupt
            try:
                engine.tick()
            except Interrupted:
                pass
            else:
                raise AssertionError("Dispatch interruption did not fire")
            from agent_runtime.store import Store
            identity = Store(engine.root).state["pending"]["id"]
            provider.transform = None
            for _ in range(3):
                engine = Controller(engine.root, reasoning=provider)
                status = engine.tick()
                require(status["status"] != "RUNNING", status)
                require(engine.state["pending"]["id"] == identity, "Lost uncertain effect binding")
            require(len(provider.calls) == engine.state["model_calls"] == 1, "Uncertain call repeated")
            return {"unknown_effect_preserved": True, "automatic_redispatches": 0, "reserved_calls": 1}

        replay = {}
        if name == "separate-work-merge-approval":
            from agent_runtime.actions import action
            from agent_runtime.io import Closed
            first = drive()
            require(first["status"] == "NEEDS_DECISION" and first["approval_purpose"] == "work-plan", first)
            require(engine.task["head"] == engine.task["base"], "Implementation preceded work authorization")
            calls = len(provider.calls)
            try:
                action(engine.root, "approve", first["approval"])
            except Closed:
                pass
            else:
                raise AssertionError("Merge command authorized work")
            require(len(provider.calls) == calls, "Wrong-purpose decision called provider")
            action(engine.root, "approve-work", first["approval"])
            engine = Controller(engine.root, reasoning=provider)
            second = drive()
            require(second["status"] == "NEEDS_DECISION" and second["approval_purpose"] == "candidate-merge", second)
            require(engine.task["resume_phase"] == "merge" and not engine.task.get("merge_sha"), "Missing merge decision")
            try:
                action(engine.root, "approve-work", second["approval"])
            except Closed:
                pass
            else:
                raise AssertionError("Work command authorized merge")
            require(first["approval"] != second["approval"], "Work and candidate authority were conflated")
            action(engine.root, "approve", second["approval"])
            engine = Controller(engine.root, reasoning=provider)
            replay = {"work_decisions": 1, "merge_decisions": 1, "wrong_purpose_rejected": True}
        if name == "model-receipt-replay":
            drive("architect")
            def interrupt(_):
                raise Interrupted()
            engine.store.after_receipt = interrupt
            try:
                engine.tick()
            except Interrupted:
                pass
            else:
                raise AssertionError("Receipt interruption did not fire")
            count, reserved = len(provider.calls), engine.state["model_calls"]
            engine = Controller(engine.root, reasoning=provider)
            engine.tick()
            require(len(provider.calls) == count and engine.state["model_calls"] == reserved,
                    "Receipt replay called or reserved the provider again")
            replay = {"receipt_replayed": True, "duplicate_calls": 0, "duplicate_reservations": 0}

        if name == "stale-review-evidence":
            drive("publish")
            original = engine.task["head"]
            engine.task["role_results"]["reviewer"]["spec_hash"] = "stale-specification"
            engine.store.save()
            status = engine.tick()
            require(status["status"] != "RUNNING", status)
            require(engine.task["head"] == original and not engine.task.get("merge_sha"), "Stale review merged")
            require(engine.repo.resolve("main") == engine.task["base"], "Stale evidence advanced main")
            return {"stale_review_blocked": True, "product_main_unchanged": True}

        if name.startswith("ci-"):
            from agent_runtime.github import GitHub
            drive("ci")
            rows = ci_rows(name)
            def transport(path, method, body):
                require("/check-runs?" in path and method == "GET", "Unexpected CI observation effect")
                return {"check_runs": [{"id": row["id"], "name": row["name"], "app": {"id": row["app_id"]},
                    "head_sha": engine.task["head"], "status": row["status"], "conclusion": row["conclusion"]}
                    for row in rows]}
            engine.github = GitHub({"repository": "owner/product", "token_env": "GH_TOKEN",
                "required_checks": [{"name": "build", "app_id": 15368}]}, "main", transport=transport)
            count = len(provider.calls)
            engine.tick()
            require(not engine.task.get("merge_sha"), "CI observation bypassed merge gate")
            return ci_outcome(name, engine.task["phase"], engine.task["repairs"], count, len(provider.calls))

        status = drive()
        if name == "working-set-authority":
            require(status["status"] == "BLOCKED_POLICY", status)
            require(engine.task["head"] == engine.task["base"] and not engine.task.get("merge_sha"), "Unauthorized edit applied")
            require(engine.state.get("pending") is None, "Rejected edit left an unrecoverable effect")
            return {"unauthorized_edit_blocked": True, "candidate_unchanged": True, "pending_effect": False}
        require(status["status"] == "COMPLETED", status)
        task = engine.state["archive"][0]
        result = delivery(task, task["independent_baseline"], task["postmerge_evidence"])
        if name == "negative-control-repair":
            require(task["repairs"] == 1, "Negative-control rejection did not consume one repair")
            require(sum(row["phase"] == "tester" for row in provider.calls) == 2, "Rejected tests were not replaced")
            result.update(repairs=1, tester_calls=2)
        return {**result, **replay}


def flow_scenario(name):
    from test_verified_git_loop import VerifiedGitLoopTests
    from flow_loop.runtime import Controller
    from helpers import policy, command
    fixture = VerifiedGitLoopTests()
    fixture.setUp()
    try:
        fixture.p = policy(verification_profile="counterfactual-regression/v1", approved_items=["TASK-1"],
                           adaptive_agent_graph=name == "adaptive-low-route",
                           challenge_review={**policy().data["challenge_review"], "enabled": False})
        state = fixture.store.load()
        state["policy_hash"] = fixture.p.fingerprint
        fixture.store.save(state, "adapter-conformance-activation")

        def restart():
            fixture.c = Controller(fixture.store, fixture.p, fixture.product, fixture.gh,
                                   fixture.a, fixture.tests, fixture.root / "spool", clock=lambda: 1700000100)
        restart()
        if name.startswith("ci-"):
            fixture.until("ci")
            fixture.gh.checks = lambda *_: ci_rows(name)
            count = len(fixture.a.calls)
            fixture.c.tick()
            task = fixture.store.load()["tasks"]["TASK-1"]
            require(fixture.gh.merges == 0, "CI observation bypassed merge gate")
            return ci_outcome(name, task["phase"], task["repairs"], count, len(fixture.a.calls))
        if name == "negative-control-repair":
            original = copy.deepcopy(fixture.a.responses["tester"])
            fixture.a.responses["tester"]["edits"][0]["content"] = original["edits"][0]["content"].replace(
                "self.assertEqual(add(-2,-3),-5)", "self.assertEqual(add(3,0),3)")
            fixture.until("independent_baseline")
            fixture.c.tick()
            task = fixture.store.load()["tasks"]["TASK-1"]
            require(task["phase"] == "tester" and task["test_receipt"]["passed"], "Rejected control lost product baseline")
            fixture.a.responses["tester"] = original
        if name == "working-set-authority":
            fixture.a.responses["developer"]["edits"].append({"path": "src/other.py", "expected_sha256": "absent",
                "delete": False, "content": "# outside the approved working set\n"})
            fixture.until("developer")
            fixture.c.tick()
            task = fixture.store.load()["tasks"]["TASK-1"]
            require(task["phase"] == "await_human", task)
            require(task["head"] == task["base"] and not task.get("merge_sha"), "Unauthorized edit applied")
            require(task.get("pending") is None, "Rejected edit left an unrecoverable effect")
            return {"unauthorized_edit_blocked": True, "candidate_unchanged": True, "pending_effect": False}
        if name == "stale-review-evidence":
            fixture.until("publish")
            state = fixture.store.load()
            task = state["tasks"]["TASK-1"]
            original = task["head"]
            task["verdicts"]["reviewer"]["spec_hash"] = "stale-specification"
            fixture.store.save(state, "adapter-conformance-stale-review")
            fixture.c.tick()
            task = fixture.store.load()["tasks"]["TASK-1"]
            require(task["phase"] == "await_human" and task["head"] == original, task)
            require(fixture.gh.created == fixture.gh.merges == 0, "Stale review published or merged")
            require(fixture.product.fetch_main() == task["base"], "Stale evidence advanced main")
            return {"stale_review_blocked": True, "product_main_unchanged": True}
        if name == "uncertain-model-fence":
            fixture.a.fail = Interrupted()
            try:
                fixture.c.tick()
            except Interrupted:
                pass
            else:
                raise AssertionError("Dispatch interruption did not fire")
            identity = fixture.store.load()["discovery_task"]["pending"]["id"]
            fixture.a.fail = None
            for _ in range(3):
                restart()
                fixture.c.tick()
                state = fixture.store.load()
                require(state["discovery_task"]["pending"]["id"] == identity, "Lost uncertain effect binding")
            require(len(fixture.a.calls) == state["daily"]["calls"] == 1, "Uncertain call repeated")
            return {"unknown_effect_preserved": True, "automatic_redispatches": 0, "reserved_calls": 1}
        replay = {}
        if name == "separate-work-merge-approval":
            fixture.a.responses["architect"]["risk"] = "high"
            first = fixture.until("await_human")
            require(first.get("approval_kind") == "work" and first["head"] == first["base"], "Work decision absent")
            work_binding = fixture.p.work_approval(first)
            calls = len(fixture.a.calls)
            fixture.gh.command_list = [command("/loop approve TASK-1 " + work_binding, cid=11)]
            fixture.c.tick()
            require(len(fixture.a.calls) == calls and fixture.store.load()["tasks"]["TASK-1"]["phase"] == "await_human",
                    "Merge command authorized work")
            fixture.gh.command_list = [command("/loop approve-work TASK-1 " + work_binding, cid=12)]
            fixture.c.tick()
            second = fixture.until("await_human")
            require(second.get("approval_kind") == "merge" and second["resume_phase"] == "merge", "Repeated work decision")
            require(fixture.gh.merges == 0, "Missing merge decision")
            merge_binding = fixture.p.candidate_approval(second)
            fixture.gh.command_list = [command("/loop approve-work TASK-1 " + merge_binding, cid=13)]
            fixture.c.tick()
            require(fixture.gh.merges == 0, "Work command authorized merge")
            require(work_binding != merge_binding, "Work and candidate authority were conflated")
            fixture.gh.command_list = [command("/loop approve TASK-1 " + merge_binding, cid=14)]
            fixture.c.tick()
            replay = {"work_decisions": 1, "merge_decisions": 1, "wrong_purpose_rejected": True}
        if name == "model-receipt-replay":
            fixture.until("architect")
            original = fixture.c.save
            def interrupt(kind, *args, **kwargs):
                if kind == "agent-receipt":
                    raise Interrupted()
                return original(kind, *args, **kwargs)
            fixture.c.save = interrupt
            try:
                fixture.c.tick()
            except Interrupted:
                pass
            else:
                raise AssertionError("Receipt interruption did not fire")
            count = len(fixture.a.calls)
            reserved = fixture.store.load()["daily"]["calls"]
            restart()
            fixture.c.tick()
            require(len(fixture.a.calls) == count and fixture.store.load()["daily"]["calls"] == reserved,
                    "Receipt replay called or reserved the provider again")
            replay = {"receipt_replayed": True, "duplicate_calls": 0, "duplicate_reservations": 0}
        task = fixture.until("done")
        result = delivery(task, task["counterfactual_receipt"], task["postmerge_machine"])
        if name == "negative-control-repair":
            require(task["repairs"] == 1, "Negative-control rejection did not consume one repair")
            require(sum(phase == "tester" for _, phase in fixture.a.calls) == 2, "Rejected tests were not replaced")
            result.update(repairs=1, tester_calls=2)
        return {**result, **replay}
    finally:
        fixture.doCleanups()


def worker(profile, reference, consumer, scenarios):
    root = reference if profile == "reference" else consumer
    sys.path[:0] = [str(root), str(root / "tests")]
    results = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for name in scenarios:
            with trace_workflow() as transitions:
                outcome = (reference_scenario if profile == "reference" else flow_scenario)(name)
            results[name] = {"outcome": outcome, "transitions": transitions}
    return {"profile": profile, "scenarios": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=ROOT)
    parser.add_argument("--worker", choices=("reference", "flow"))
    parser.add_argument("--scenario", action="append", choices=SCENARIOS)
    args = parser.parse_args()
    reference, consumer = args.reference.resolve(), args.consumer.resolve()
    scenarios = args.scenario or SCENARIOS
    if args.worker:
        print(json.dumps(worker(args.worker, reference, consumer, scenarios)))
        return
    sys.path.insert(0, str(reference / "scripts"))
    from sync_control_core import check, inventory
    check(consumer)
    if inventory(reference) != inventory(consumer):
        raise SystemExit("Adapter comparison requires identical reviewed core bytes")
    profiles = []
    for profile in ("reference", "flow"):
        command = [sys.executable, "-S", str(Path(__file__).resolve()), "--reference", str(reference),
                   "--consumer", str(consumer), "--worker", profile]
        for scenario in scenarios:
            command.extend(["--scenario", scenario])
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise SystemExit(profile + " conformance failed:\n" + result.stderr[-8000:])
        profiles.append(json.loads(result.stdout))
    if profiles[0]["scenarios"] != profiles[1]["scenarios"]:
        differences = {name: {row["profile"]: row["scenarios"][name] for row in profiles}
                       for name in scenarios if profiles[0]["scenarios"][name] != profiles[1]["scenarios"][name]}
        raise SystemExit("Adapter behavior drift: " + json.dumps(differences, indent=2))
    print(json.dumps({"schema": 2, "passed": True, "scope": "actual-adapter-workflow-parity",
                      "live_providers": False, "real_git": True, "real_fixture_execution": True,
                      "profiles": profiles}, indent=2))


if __name__ == "__main__":
    main()
