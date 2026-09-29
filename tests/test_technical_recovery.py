"""Real durable state and Git with controlled transport failures."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_runtime.actions import action
from agent_runtime.controller import Controller
from agent_runtime.io import Closed, ExternalPending, NotDispatched, Unavailable
from agent_runtime.store import Store
from agent_runtime.service import RunService
from runtime_support import build_product, goal, policy, InProcessProvider


class TechnicalRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); product = self.root / "product"
        build_product(product)
        self.engine = Controller.start(self.root / "run", policy(product), goal(), trusted_local=True)
        self.now = 1000; self.engine.clock = lambda: self.now

    def restart(self):
        self.engine = Controller(self.engine.root, clock=lambda: self.now)

    def test_not_dispatched_reservation_survives_restart_and_deadline(self):
        with patch("agent_runtime.reasoning.run", side_effect=NotDispatched("no child")):
            self.assertEqual(self.engine.tick()["status"], "WAITING_EXTERNAL")
        pending = copy.deepcopy(self.engine.state["pending"])
        self.assertEqual(pending["dispatch_state"], "not_started")
        self.assertEqual(self.engine.state["model_calls"], 1)
        from agent_runtime.usage import usage_report
        usage = usage_report(self.engine.store)
        self.assertEqual((usage["reserved_calls"], usage["not_dispatched"], usage["unknown_outcomes"]), (1, 1, 0))
        report = RunService(self.engine.root).explain()
        self.assertEqual(report["next_action"]["id"], "tick")
        self.assertIsNone(report["pending_receipt"])
        self.assertFalse({"retry-effect", "reconcile-effect"} & set(report["decision"]["actions"]))
        self.assertEqual(report["status"]["technical_recovery"], self.engine.state["technical_recovery"])
        with self.assertRaises(Closed): action(self.engine.root, "retry-effect", pending["id"])
        self.restart()
        with patch("agent_runtime.reasoning.run", side_effect=AssertionError("before deadline")):
            self.assertEqual(self.engine.tick()["status"], "WAITING_EXTERNAL")
        self.assertEqual(self.engine.state["pending"], pending)
        self.now = self.engine.state["technical_recovery"]["next_attempt"]
        self.assertEqual(self.engine.tick()["status"], "RUNNING")
        self.assertEqual(self.engine.state["model_calls"], 1)
        self.assertIn(pending["id"], self.engine.state["receipts"])

    def test_unknown_model_outcome_never_enters_automatic_retry(self):
        with patch("agent_runtime.reasoning.run", side_effect=Unavailable("response lost")) as provider:
            self.assertEqual(self.engine.tick()["status"], "BLOCKED_POLICY")
            pending = copy.deepcopy(self.engine.state["pending"])
            self.assertEqual(self.engine.state["diagnostic"]["code"], "MODEL_OUTCOME_UNKNOWN")
            self.now += 10000; self.restart(); self.engine.tick()
            self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.engine.state["pending"], pending)
        self.assertNotIn("technical_recovery", self.engine.state)
        with self.assertRaises(Closed): action(self.engine.root, "retry")

    def test_exhaustion_survives_restart_and_explicit_continue_preserves_budget(self):
        for attempt in range(7):
            self.restart()
            with patch("agent_runtime.reasoning.Reasoning.prepare", side_effect=Unavailable("offline")):
                result = self.engine.tick()
            checkpoint = self.engine.state["technical_recovery"]
            self.assertEqual(checkpoint["attempts"], attempt + 1)
            self.now = checkpoint["next_attempt"]
        self.assertEqual(result["status"], "FAILED")
        self.restart()
        with patch("agent_runtime.reasoning.run", side_effect=AssertionError("exhausted")):
            self.assertEqual(self.engine.tick()["status"], "FAILED")
        before = self.engine.state["model_calls"]
        report = RunService(self.engine.root).explain()
        self.assertEqual(report["next_action"]["id"], "continue")
        self.assertTrue(report["decision"]["technical_continue_allowed"])
        self.assertFalse({"replan", "retry"} & set(report["decision"]["actions"]))
        self.assertIn("preserving", report["next_action"]["condition"])
        action(self.engine.root, "continue")
        self.restart(); self.engine.reasoning = InProcessProvider()
        self.assertEqual(self.engine.tick()["status"], "RUNNING")
        self.assertEqual(self.engine.state["model_calls"], before + 1)
        self.assertEqual(len(self.engine.state["technical_recovery_history"]), 1)

    def test_completed_receipt_replays_after_backoff_without_dispatch_or_cost(self):
        self.engine.store.after_receipt = lambda _: (_ for _ in ()).throw(Unavailable("lost acknowledgement"))
        self.assertEqual(self.engine.tick()["status"], "WAITING_EXTERNAL")
        self.assertIsNotNone(self.engine.state["pending"])
        self.now = self.engine.state["technical_recovery"]["next_attempt"]
        self.restart()
        with patch("agent_runtime.reasoning.run", side_effect=AssertionError("duplicate call")), \
                patch("agent_runtime.reasoning.Reasoning.prepare", side_effect=AssertionError("receipt preparation")):
            self.assertEqual(self.engine.tick()["status"], "RUNNING")
        self.assertEqual(self.engine.state["model_calls"], 1)
        self.assertIsNone(self.engine.state["pending"])

    def test_pending_observation_does_not_consume_technical_retry_budget(self):
        for _ in range(9):
            with patch.object(self.engine, "reconcile", side_effect=ExternalPending("checks pending")):
                self.assertEqual(self.engine.tick()["status"], "WAITING_EXTERNAL")
        self.assertNotIn("technical_recovery", self.engine.state)
        self.assertEqual(self.engine.state["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
