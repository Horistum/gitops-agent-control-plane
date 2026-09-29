"""Real reference-adapter work and merge authority boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path

from agent_runtime.actions import action
from agent_runtime.authorization import approval_binding, work_binding
from agent_runtime.controller import Controller
from agent_runtime.decisions import decision_document
from agent_runtime.io import Closed
from agent_runtime.roles import repair
from agent_runtime.service import RunService
from runtime_support import InProcessProvider, build_product, goal, policy


class WorkAuthorizationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.product = self.root / "product"
        build_product(self.product)
        self.policy, self.goal = policy(self.product), goal()
        self.policy.update(adaptive_agent_graph=True, challenge=False)
        self.goal["items"][0]["risk"] = "high"

    def start(self, provider=None):
        engine = Controller.start(self.root / "run", self.policy, self.goal, trusted_local=True)
        engine.reasoning = provider or InProcessProvider()
        return engine

    def drive(self, engine, phase=None):
        for _ in range(140):
            result = engine.tick()
            if result["status"] != "RUNNING" or result["phase"] == phase:
                return result
        self.fail("Run failed to converge")

    def authorize(self, engine, name="approve-work"):
        document = decision_document(engine.state)
        action(engine.root, name, document["binding"], decision_hash=document["decision_hash"])
        return Controller(engine.root, reasoning=engine.reasoning)

    def test_high_attempt_has_one_work_hold_then_one_exact_merge_hold(self):
        provider = InProcessProvider()
        engine = self.start(provider)
        held = self.drive(engine)
        self.assertEqual((held["status"], held["approval_purpose"]), ("NEEDS_DECISION", "work-plan"))
        self.assertEqual(engine.task["head"], engine.task["base"])
        self.assertNotIn("developer", [call["phase"] for call in provider.calls])
        document = decision_document(engine.state)
        self.assertEqual(document["work_plan"]["working_files"], ["app.py"])
        self.assertEqual(RunService(engine.root).explain()["next_action"]["id"], "approve-work")
        work = held["approval"]
        engine = self.authorize(engine)
        held = self.drive(engine)
        self.assertEqual((held["status"], held["approval_purpose"]), ("NEEDS_DECISION", "candidate-merge"))
        self.assertEqual(engine.task["resume_phase"], "merge")
        self.assertEqual(engine.task["work_approval"], work)
        self.assertEqual(work_binding(engine.state), work)
        self.assertNotEqual(held["approval"], work)
        self.assertNotEqual(engine.task["head"], engine.task["base"])
        engine = self.authorize(engine, "approve")
        result = self.drive(engine)
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual([row["action"] for row in engine.state["human_actions"]], ["approve-work", "approve"])

    def test_scoped_developer_repair_preserves_work_authorization(self):
        fixed = []
        def repair_once(payload, result, _):
            if payload["phase"] == "reviewer" and not fixed:
                fixed.append(True)
                result.update(verdict="fix", summary="Repair this implementation within the accepted plan")
        engine = self.start(InProcessProvider(repair_once))
        self.drive(engine)
        engine = self.authorize(engine)
        work = engine.task["work_approval"]
        result = self.drive(engine)
        self.assertEqual(result["approval_purpose"], "candidate-merge", result)
        self.assertEqual(engine.task["repairs"], 1)
        self.assertEqual(engine.task["work_approval"], work_binding(engine.state))
        self.assertEqual(engine.task["work_approval"], work)

    def test_planning_repair_revokes_work_before_implementation(self):
        engine = self.start()
        self.drive(engine)
        engine = self.authorize(engine)
        repair(engine, "architect", {"phase": "reviewer", "summary": "Revisit the plan"})
        self.assertNotIn("work_approval", engine.task)
        engine.store.save()
        result = self.drive(engine)
        self.assertEqual(result["approval_purpose"], "work-plan")
        self.assertEqual(engine.task["head"], engine.task["base"])

    def test_commands_reject_cross_purpose_stale_and_legacy_authority(self):
        engine = self.start()
        held = self.drive(engine)
        with self.assertRaisesRegex(Closed, "candidate.*purpose"):
            action(engine.root, "approve", held["approval"])
        with self.assertRaisesRegex(Closed, "work-plan.*purpose"):
            action(engine.root, "approve-work", approval_binding(engine.state))
        stale = held["approval"]
        engine.task["plan"].append("Changed work obligation")
        engine.store.save()
        with self.assertRaisesRegex(Closed, "work-plan.*purpose"):
            action(engine.root, "approve-work", stale)
        # Legacy candidate authority must not silently populate work authority.
        engine.task.update(approval=work_binding(engine.state), phase="developer")
        engine.state["status"] = "RUNNING"
        engine.store.save()
        held = self.drive(engine)
        self.assertEqual(held["approval_purpose"], "work-plan")
        engine = self.authorize(engine)
        held = self.drive(engine)
        with self.assertRaisesRegex(Closed, "work-plan.*purpose"):
            action(engine.root, "approve-work", held["approval"])
        with self.assertRaisesRegex(Closed, "candidate.*purpose"):
            action(engine.root, "approve", engine.task["work_approval"])
        candidate = held["approval"]
        engine.task["head"] = "changed-candidate"
        engine.store.save()
        with self.assertRaisesRegex(Closed, "candidate.*purpose"):
            action(engine.root, "approve", candidate)

    def test_legacy_merge_hold_cannot_be_approved_without_explicit_purpose(self):
        self.goal["items"][0]["risk"] = "low"
        self.goal["auto_merge_ceiling"] = "none"
        engine = self.start()
        result = self.drive(engine)
        self.assertEqual(result["approval_purpose"], "candidate-merge")
        engine.task.pop("approval_purpose")
        engine.store.save()
        self.assertFalse(decision_document(engine.state)["approvable"])
        with self.assertRaisesRegex(Closed, "candidate.*purpose"):
            action(engine.root, "approve", result["approval"])

    def test_work_binding_ignores_head_but_detects_authority_and_scope_drift(self):
        self.policy["critical_paths"] = ["*.py"]
        engine = self.start()
        self.drive(engine)
        initial = work_binding(engine.state)
        original = copy.deepcopy(engine.state)
        engine.task["head"] = "changed-head"
        engine.task["candidate_critical_paths"] = ["app.py"]
        self.assertEqual(work_binding(engine.state), initial)
        mutations = [
            lambda s: s["task"].update(base="another-base"),
            lambda s: s["task"].update(attempt=2),
            lambda s: s["task"].update(spec_hash="another-spec"),
            lambda s: s["task"]["plan"].append("Another plan step"),
            lambda s: s["task"]["test_design"].append({"criterion_id": "AC-2", "description": "More tests"}),
            lambda s: s["task"]["working_set"].append("other.py"),
            lambda s: s["task"].update(candidate_critical_paths=["unexpected.py"]),
            lambda s: s.update(policy_hash="another-policy"),
            lambda s: s["goal"].update(objective="Different goal"),
        ]
        for mutate in mutations:
            state = copy.deepcopy(original)
            mutate(state)
            self.assertNotEqual(work_binding(state), initial)

    def test_late_high_assessment_holds_before_applying_edits(self):
        self.goal["items"][0]["risk"] = "low"
        def escalate(payload, result, _):
            if payload["phase"] == "developer":
                result["risk"] = "high"
        engine = self.start(InProcessProvider(escalate))
        result = self.drive(engine)
        self.assertEqual((result["status"], result["approval_purpose"]), ("NEEDS_DECISION", "work-plan"))
        self.assertEqual(engine.task["head"], engine.task["base"])
        self.assertEqual(engine.repo.read(engine.task["head"], "app.py"), (self.product / "app.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
