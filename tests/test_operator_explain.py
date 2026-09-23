"""Operator projections must explain recovery without dispatch or authority drift."""
import contextlib
import http.client
import io
import itertools
import json
from pathlib import Path
import shlex
import tempfile
import threading
import unittest
from unittest.mock import patch

from control_plane_core import required_reviews, workflow_transition
from agent_runtime.actions import action, upgrade
from agent_runtime.cli import main
from agent_runtime.controller import Controller
from agent_runtime.diagnostics import record
from agent_runtime.explain import workflow_document, workflow_path
from agent_runtime.io import Closed, locked
from agent_runtime.review import create_server
from agent_runtime.service import RunService
from agent_runtime.store import Store
from runtime_support import InProcessProvider, build_product, goal, policy


class Crash(BaseException):
    pass


class OperatorExplainTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.product = self.root / "product"
        build_product(self.product)
        self.policy = policy(self.product)

    def start(self, *, approval=False):
        # Copyable POSIX commands must also handle quotes and spaces in a path.
        engine = Controller.start(self.root / "owner's run", self.policy, goal(approval=approval), trusted_local=True)
        engine.reasoning = InProcessProvider()
        return engine

    def drive(self, engine, phase=None):
        for _ in range(100):
            result = engine.tick()
            if result["status"] != "RUNNING" or result["phase"] == phase:
                return result
        self.fail("Fixture did not converge")

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(list(args)), 0)
        return output.getvalue()

    def test_explain_observes_one_snapshot_without_writing_or_dispatching(self):
        engine = self.start(); service = RunService(engine.root)
        before = {p.relative_to(engine.root): p.read_bytes() for p in engine.root.rglob("*") if p.is_file()}
        decision = service.decision()
        with locked(engine.root), patch("agent_runtime.reasoning.run", side_effect=AssertionError("model dispatched")):
            report = service.explain()
        after = {p.relative_to(engine.root): p.read_bytes() for p in engine.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(report["decision"], decision)
        self.assertEqual(report["next_action"]["id"], "tick")
        self.assertEqual(shlex.split(report["next_action"]["command"]),
                         ["agent-control", "tick", "--state", str(engine.root)])
        self.assertEqual(report["usage"]["reserved_calls"], 0)

    def test_default_json_remains_and_human_formats_expose_result_and_exact_binding(self):
        engine = self.start()
        status = json.loads(self.cli("status", "--state", str(engine.root)))
        self.assertEqual(status, RunService(engine.root).status())
        self.assertEqual(status["product"]["base_ref_sha"], engine.repo.resolve("refs/heads/main"))
        for command in ("status", "decision"):
            output = self.cli(command, "--state", str(engine.root), "--format", "table")
            self.assertIn(engine.state["run_id"], output)
            self.assertIn("Phase", output)
        decision = json.loads(self.cli("decision", "--state", str(engine.root)))
        self.assertEqual(decision, RunService(engine.root).decision())
        self.assertIn("Next step", self.cli("explain", "--state", str(engine.root)))
        self.assertEqual(json.loads(self.cli("explain", "--state", str(engine.root), "--format", "json"))["decision"], decision)

    def test_uncertain_call_never_defaults_to_paid_retry_and_read_does_not_spend(self):
        engine = self.start()
        with patch.object(engine.reasoning, "execute", side_effect=Crash):
            with self.assertRaises(Crash):
                engine.tick()
        before = (engine.root / "state.json").read_bytes()
        report = RunService(engine.root).explain()
        self.assertIsNone(report["next_action"])
        self.assertIn("model effect is pending", report["summary"])
        self.assertEqual(report["usage"]["unknown_outcomes"], 1)
        actions = {row["id"]: row for row in report["actions"]}
        self.assertEqual(set(actions), {"pause", "reconcile-effect", "retry-effect"})
        self.assertFalse(actions["reconcile-effect"]["enabled"])
        self.assertTrue(actions["retry-effect"]["enabled"])
        self.assertIn("charged", actions["retry-effect"]["condition"])
        self.assertEqual(shlex.split(actions["retry-effect"]["command"])[-2:],
                         ["--binding", engine.state["pending"]["id"]])
        self.assertEqual((engine.root / "state.json").read_bytes(), before)

    def test_short_inferred_values_do_not_corrupt_cli_run_ids_or_approval_bindings(self):
        engine = self.start(approval=True); self.drive(engine)
        service = RunService(engine.root)
        status, decision = service.status(), service.decision()
        with patch("agent_runtime.diagnostics.secret_values", return_value=["1", "e", "true"]):
            for command in ("status", "decision"):
                output = self.cli(command, "--state", str(engine.root), "--format", "table")
                self.assertIn(status["run_id"], output)
                self.assertIn(status["head"], output)
                if command == "decision":
                    self.assertIn(decision["binding"], output)
                    self.assertIn(decision["decision_hash"], output)
            output = self.cli("explain", "--state", str(engine.root))
            self.assertIn(status["run_id"], output)
            self.assertIn(decision["binding"], output)
            self.assertIn(decision["decision_hash"], output)

    def test_durable_model_receipt_selects_reconciliation_and_preserves_budget(self):
        engine = self.start()
        engine.store.after_receipt = lambda _: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash): engine.tick()
        service = RunService(engine.root); report = service.explain()
        self.assertEqual(report["next_action"]["id"], "reconcile-effect")
        self.assertTrue(report["pending_receipt"]["present"])
        self.assertFalse(next(row for row in report["actions"] if row["id"] == "retry-effect")["enabled"])
        args = shlex.split(report["next_action"]["command"])[1:]
        self.cli(*args)
        engine = Controller(engine.root, reasoning=InProcessProvider()); engine.tick()
        self.assertEqual(engine.state["model_calls"], 1)
        self.assertEqual(engine.reasoning.calls, [])

    def test_exhausted_budget_and_changed_authority_cannot_be_hidden_by_recovery_hints(self):
        self.policy["limits"]["model_calls"] = 1
        engine = self.start()
        with patch.object(engine.reasoning, "execute", side_effect=Crash):
            with self.assertRaises(Crash): engine.tick()
        report = RunService(engine.root).explain()
        retry = next(row for row in report["actions"] if row["id"] == "retry-effect")
        self.assertFalse(retry["enabled"])
        self.assertIn("No model-call budget remains", retry["condition"])
        self.assertIsNone(report["next_action"])
        store = Store(engine.root)
        store.state["goal"]["objective"] = "Changed saved authority"
        store.save()
        report = RunService(engine.root).explain()
        self.assertEqual(report["diagnostic"]["code"], "AUTHORITY_CHANGED")
        self.assertEqual(report["actions"], [])
        self.assertIsNone(report["next_action"])

    def test_nonmodel_effect_is_distinct_from_retry_and_from_model_reconciliation(self):
        engine = self.start(); self.drive(engine, "apply_developer")
        engine.store.after_receipt = lambda _: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash): engine.tick()
        report = RunService(engine.root).explain()
        self.assertEqual(report["next_action"]["id"], "reconcile")
        self.assertNotIn("retry-effect", [row["id"] for row in report["actions"]])
        self.assertIsNone(report["pending_receipt"])

    def test_drift_recommends_pause_then_only_eligible_upgrade(self):
        engine = self.start(); service = RunService(engine.root)
        with contextlib.ExitStack() as stack:
            for name in ("store", "controller", "actions"):
                stack.enter_context(patch("agent_runtime." + name + ".runtime_fingerprint", return_value="f" * 64))
            report = service.explain()
            self.assertEqual(report["next_action"]["id"], "pause")
            action(engine.root, "pause")
            report = service.explain()
            self.assertEqual(report["next_action"]["id"], "upgrade")
            self.assertNotIn("--suspend", report["next_action"]["command"])
            self.assertTrue(upgrade(engine.root)["upgraded"])
        # No guessed upgrade while an unmerged active attempt has changed code.
        engine = self.start_at_second_root()
        self.drive(engine, "verify"); action(engine.root, "pause")
        with patch("agent_runtime.store.runtime_fingerprint", return_value="e" * 64):
            report = RunService(engine.root).explain()
        self.assertIsNone(report["next_action"])
        self.assertNotIn("upgrade", [row["id"] for row in report["actions"]])

    def start_at_second_root(self):
        engine = Controller.start(self.root / "second", self.policy, goal(), trusted_local=True)
        engine.reasoning = InProcessProvider()
        return engine

    def test_unknown_failure_stays_specific_and_pausing_does_not_suggest_continue_as_recovery(self):
        engine = self.start()
        def broken(*_):
            try:
                raise ValueError("malformed local observation")
            except ValueError as exc:
                raise RuntimeError("unfamiliar controller bug") from exc
        with patch.object(engine, "reconcile", broken):
            engine.tick()
        action(engine.root, "pause")
        report = RunService(engine.root).explain()
        self.assertIsNone(report["next_action"])
        self.assertEqual(report["diagnostic"]["code"], "UNEXPECTED_ERROR")
        self.assertEqual(report["diagnostics"]["events"][-1]["id"], report["diagnostic"]["id"])
        rendered = self.cli("explain", "--state", str(engine.root))
        self.assertIn("malformed local observation", rendered)
        self.assertIn("RuntimeError", rendered)
        self.assertIn("test_operator_explain.py:", rendered)
        self.assertIn("Only removes pause", rendered)

    def test_approval_command_keeps_exact_hash_while_logs_and_git_observation_change(self):
        engine = self.start(approval=True); self.drive(engine)
        service = RunService(engine.root); report = service.explain()
        self.assertEqual(report["next_action"]["id"], "approve")
        self.assertIn("Negative control", report["evidence_summaries"]["independent_baseline"])
        record(engine.root, engine.state, exc=Closed("a later observation"), operation="test")
        # A read-only ref observation is not part of the approval decision hash.
        engine.repo.text("update-ref", "refs/heads/main", engine.task["head"])
        after = service.explain()
        self.assertEqual(after["decision"], report["decision"])
        self.assertNotEqual(after["status"]["product"]["base_ref_sha"], report["status"]["product"]["base_ref_sha"])
        args = shlex.split(after["next_action"]["command"])
        self.assertEqual(args[args.index("--decision-hash") + 1], after["decision"]["decision_hash"])
        # A real owner state change still invalidates the displayed decision.
        action(engine.root, "pause")
        with self.assertRaisesRegex(Closed, "Displayed decision changed"):
            service.approve(after["decision"]["binding"], after["decision"]["decision_hash"])

    def test_completed_result_is_in_run_repository_and_checkout_is_unchanged(self):
        engine = self.start()
        original = (self.product / "app.py").read_bytes()
        self.assertEqual(self.drive(engine)["status"], "COMPLETED")
        report = RunService(engine.root).explain()
        product = report["status"]["product"]
        self.assertEqual(product["repository"], str(engine.root / "product.git"))
        self.assertEqual(product["source_checkout"], str(self.product))
        self.assertEqual(product["base_ref_sha"], report["status"]["merge_sha"])
        self.assertIn(b"return 2", engine.repo.read(product["base_ref_sha"], "app.py"))
        self.assertEqual((self.product / "app.py").read_bytes(), original)
        self.assertIsNone(report["next_action"])

    def test_missing_sections_cannot_hide_cause_and_logs_are_bounded(self):
        engine = self.start(); engine.tick()
        state = Store(engine.root).state
        for i in range(4):
            record(engine.root, state, exc=Closed("event " + str(i)))
        self.assertEqual(len(RunService(engine.root).explain(2)["diagnostics"]["events"]), 2)
        with patch("agent_runtime.explain.recent_events", side_effect=OSError("log unreadable")), \
             patch("agent_runtime.explain.usage_report", side_effect=Closed("receipt unavailable")), \
             patch("agent_runtime.git.GitRepository.resolve", side_effect=Closed("repository unavailable")):
            report = RunService(engine.root).explain()
        self.assertEqual(len(report["warnings"]), 2)
        self.assertIn("repository unavailable", report["status"]["product"]["inspection_error"])
        self.assertEqual(report["usage"]["reserved_calls"], 1)
        self.assertIsNone(report["usage"]["recorded_calls"])
        for bad in (0, 101, True):
            with self.assertRaises(Closed): RunService(engine.root).explain(bad)

    def test_workflow_routes_cover_all_modifiers_and_match_actual_reducer(self):
        for risk, adaptive, critical, challenge in itertools.product(("low", "medium", "high"), (True, False), (False, True), (False, True)):
            args = dict(risk=risk, adaptive=adaptive, critical=critical, challenge=challenge)
            with self.subTest(**args):
                phases = workflow_path(**args)
                frame = {"phase": "baseline", **args}
                self.assertEqual(phases[-1], "done")
                for source, target in zip(phases, phases[1:]):
                    frame["phase"] = source
                    self.assertEqual(workflow_transition(frame, {"kind": "advance"})["phase"], target)
                self.assertTrue(set(required_reviews(frame)).issubset(phases))
                high = risk == "high" or critical or not adaptive
                self.assertEqual("chief_accept" in phases, high)
                self.assertEqual("challenge_review" in phases, challenge)
        engine = self.start(); self.drive(engine, "apply_developer")
        view = workflow_document(engine.state)
        self.assertEqual([row["id"] for row in view["phases"] if row["current"]], ["apply_developer"])
        self.assertIn("not a completion percentage", view["note"])

    def test_explain_http_is_authenticated_and_uses_same_decision_under_writer_lock(self):
        engine = self.start(); token = "test-only-review-" + "x" * 40
        server = create_server(engine.root, token, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=2)))
        def get(auth):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("GET", "/api/explain", headers={"Authorization": "Bearer " + auth})
            response = connection.getresponse(); result = response.status, json.loads(response.read())
            connection.close(); return result
        self.assertEqual(get("wrong")[0], 401)
        with locked(engine.root):
            code, report = get(token)
        self.assertEqual(code, 200)
        self.assertEqual(report["decision"], RunService(engine.root).decision())
        self.assertEqual(report["status"], RunService(engine.root).status())


if __name__ == "__main__":
    unittest.main()
