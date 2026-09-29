"""Outer effect recovery from an exact durable worker result after a process crash."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_runtime.actions import action
from agent_runtime.controller import Controller
from agent_runtime.io import Closed, atomic_json, read_json
from control_plane_core import fingerprint
from runtime_support import build_product, goal, policy, proposal


class Crash(BaseException):
    pass


class DurableWorker:
    """Controlled journal boundary; outer integration never calls a live provider."""
    def __init__(self, path):
        self.path = path
        self.calls = 0
        self.crash = True

    def execute(self, payload):
        self.calls += 1
        result = {"result": proposal(payload), "usage": {}}
        atomic_json(self.path, {"request_hash": fingerprint(payload), "result": result})
        if self.crash:
            raise Crash()
        return result

    def recover_completed(self, payload):
        if not self.path.exists():
            return None
        saved = read_json(self.path)
        if saved["request_hash"] != fingerprint(payload):
            raise Closed("Worker journal request differs")
        return saved["result"]


class WorkerReceiptRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        product = self.root / "product"
        build_product(product)
        self.engine = Controller.start(self.root / "run", policy(product), goal(), trusted_local=True)
        self.worker = DurableWorker(self.root / "inner-result.json")
        self.engine.reasoning = self.worker

    def crash(self):
        with self.assertRaises(Crash):
            self.engine.tick()
        pending = copy.deepcopy(self.engine.state["pending"])
        self.assertEqual(pending["dispatch_state"], "dispatched")
        self.assertFalse((self.engine.root / "receipts" / (pending["id"] + ".json")).exists())
        return pending

    def test_restart_promotes_inner_result_without_preparation_dispatch_or_reservation(self):
        self.crash()
        self.engine = Controller(self.engine.root, reasoning=self.worker)
        with patch.object(self.worker, "execute", side_effect=AssertionError("duplicate dispatch")), \
                patch.object(self.worker, "prepare", side_effect=AssertionError("authentication"), create=True):
            self.assertEqual(self.engine.tick()["status"], "RUNNING")
        self.assertEqual(self.engine.state["model_calls"], 1)
        self.assertEqual(self.worker.calls, 1)
        self.assertIsNone(self.engine.state["pending"])

    def test_owner_reconciliation_recovers_inner_result_from_held_state(self):
        pending = self.crash()
        self.engine = Controller(self.engine.root, reasoning=self.worker)
        with patch.object(self.worker, "recover_completed", return_value=None):
            self.assertEqual(self.engine.tick()["status"], "BLOCKED_POLICY")
        with patch("agent_runtime.actions.Controller", side_effect=lambda root: Controller(root, reasoning=self.worker)), \
                patch.object(self.worker, "execute", side_effect=AssertionError("duplicate dispatch")), \
                patch.object(self.worker, "prepare", side_effect=AssertionError("authentication"), create=True):
            action(self.engine.root, "reconcile-effect", pending["id"])
            self.engine = Controller(self.engine.root, reasoning=self.worker)
            self.assertEqual(self.engine.tick()["status"], "RUNNING")
        self.assertEqual(self.engine.state["model_calls"], 1)
        self.assertEqual(self.worker.calls, 1)

    def test_paid_retry_refuses_completed_inner_result(self):
        pending = self.crash()
        with patch("agent_runtime.actions.Controller", side_effect=lambda root: Controller(root, reasoning=self.worker)):
            with self.assertRaisesRegex(Closed, "reconciled, not repeated"):
                action(self.engine.root, "retry-effect", pending["id"])
        self.engine = Controller(self.engine.root, reasoning=self.worker)
        self.assertEqual(self.engine.state["pending"]["id"], pending["id"])
        self.assertEqual(self.engine.state["model_calls"], 1)
        self.assertEqual(self.worker.calls, 1)


if __name__ == "__main__":
    unittest.main()
