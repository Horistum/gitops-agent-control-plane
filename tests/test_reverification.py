"""Exact verification recovery through real operational state and Git effects."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agent_runtime.actions import action
from agent_runtime.controller import Controller
from agent_runtime.decisions import decision_document
from agent_runtime.io import Closed
from agent_runtime.reverification import recovery_binding
from agent_runtime.service import RunService
from runtime_support import build_product, goal, policy, InProcessProvider


class ReverificationTests(unittest.TestCase):
    def fixture(self, phase):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); build_product(root / "product")
        engine = Controller.start(root / "run", policy(root / "product"), goal(), trusted_local=True)
        engine.reasoning = InProcessProvider()
        for _ in range(80):
            if engine.task and engine.task["phase"] == phase: return engine
            result = engine.tick()
            self.assertEqual(result["status"], "RUNNING", result)
        self.fail("Fixture did not reach " + phase)

    def inject_failure(self, engine):
        observe = engine.verification.observe
        def unavailable(*args, **kwargs):
            receipt = observe(*args, **kwargs)
            receipt["passed"] = False
            receipt["commands"].append({"argv": ["controlled-external-dependency"], "exit_code": 2})
            receipt["junit"]["error_identities"] = ["controlled.external.Dependency"]
            return receipt
        with patch.object(engine.verification, "observe", side_effect=unavailable):
            self.assertEqual(engine.tick()["status"], "FAILED")

    def test_actual_failed_verification_creates_an_executable_owner_action(self):
        for phase in ("baseline", "independent_verify", "postmerge"):
            with self.subTest(phase=phase):
                engine = self.fixture(phase); self.inject_failure(engine)
                report = RunService(engine.root).explain()
                self.assertEqual(report["next_action"]["id"], "reverify")
                document = decision_document(engine.state)
                before = copy.deepcopy(engine.state)
                receipts = {p.name: p.read_bytes() for p in (engine.root / "receipts").glob("*.json")}
                action(engine.root, "reverify", document["reverification_binding"], decision_hash=document["decision_hash"])
                engine = Controller(engine.root)
                result = engine.tick()
                self.assertIn(result["status"], {"RUNNING", "COMPLETED"}, result)
                task = engine.task or engine.state["archive"][-1]
                self.assertEqual(engine.state["model_calls"], before["model_calls"])
                self.assertEqual(engine.state["effect_epoch"], before["effect_epoch"])
                for key in ("attempt", "repairs", "frozen_tests", "head", "base", "spec_hash"):
                    self.assertEqual(task.get(key), before["task"].get(key))
                self.assertEqual(task["verification_recovery_history"][0], before["task"]["verification_recovery"])
                for name, content in receipts.items(): self.assertEqual((engine.root / "receipts" / name).read_bytes(), content)
                self.assertGreater(len(list((engine.root / "receipts").glob("*.json"))), len(receipts))

    def test_no_authority_drift_pending_effect_or_approval_can_reuse_the_binding(self):
        engine = self.fixture("independent_verify"); self.inject_failure(engine)
        original = copy.deepcopy(engine.state)
        for fields in ({"head": "a" * 40}, {"base": "a" * 40}, {"spec_hash": "changed"},
                       {"work_approval": {"binding": "revoked"}}, {"approval": {"binding": "revoked"}},
                       {"frozen_tests": {}}, {"working_set": []}, {"approvable": True}, {"hold_kind": "BLOCKED_POLICY"}):
            changed = copy.deepcopy(original); changed["task"].update(fields)
            self.assertIsNone(recovery_binding(changed))
        for fields in ({"pending": {"kind": "model"}}, {"policy_hash": "different"},
                       {"runtime_hash": "different"}, {"goal": {"objective": "different"}}):
            self.assertIsNone(recovery_binding({**original, **fields}))
        with self.assertRaises(Closed): action(engine.root, "reverify", "0" * 64)
        with self.assertRaises(Closed): action(engine.root, "retry")

    def test_bounded_reverification_survives_restart_without_consuming_replans(self):
        engine = self.fixture("baseline"); self.inject_failure(engine)
        before = engine.state["model_calls"]
        for count in range(1, 4):
            action(engine.root, "reverify", recovery_binding(engine.state))
            engine = Controller(engine.root); self.inject_failure(engine)
            self.assertEqual(engine.task["reverifications"], count)
        self.assertIsNone(recovery_binding(engine.state))
        self.assertNotIn("reverify", decision_document(engine.state)["actions"])
        self.assertEqual(engine.state["model_calls"], before)
        self.assertFalse(engine.state.get("owner_replans"))
