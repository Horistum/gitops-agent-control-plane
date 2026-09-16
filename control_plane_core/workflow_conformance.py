"""Portable aggregate contract; run unchanged by every production consumer."""
import copy
import unittest
from . import CoreError, workflow_transition, require_workflow_evidence


class WorkflowConformance(unittest.TestCase):
    def test_late_escalation_inserts_missing_plan_gates_and_invalidates_release_authority(self):
        state = {"phase": "reviewer", "risk": "low", "completed": ["architect", "developer", "tester"]}
        decision = workflow_transition(state, {"kind": "risk", "risk": "high"})
        self.assertEqual(decision["phase"], "test_design")
        self.assertEqual(decision["return_phase"], "verify")
        self.assertEqual(set(decision["invalidated"]), {"candidate", "reviews", "ci", "approval"})
        decision = workflow_transition(decision, {"kind": "advance"})
        self.assertEqual(decision["phase"], "chief_plan")
        decision = workflow_transition(decision, {"kind": "advance"})
        self.assertEqual(decision["phase"], "verify")
        self.assertNotIn("return_phase", decision)
        self.assertEqual(state["risk"], "low")

    def test_replanning_does_not_reuse_completed_design_or_release_proofs(self):
        decision = workflow_transition({"phase": "ci", "risk": "high",
            "completed": ["architect", "test_design", "chief_plan", "reviewer", "chief_accept"]},
            {"kind": "repair", "target": "architect"})
        self.assertEqual(decision["completed"], [])
        self.assertIn("plan", decision["invalidated"])
        self.assertIn("ci", decision["invalidated"])
        with self.assertRaises(CoreError):
            workflow_transition({"phase": "postmerge", "risk": "low", "merge_sha": "a" * 40},
                                {"kind": "repair", "target": "developer"})

    def test_negative_control_repair_cannot_replace_frozen_assertions(self):
        state = {"phase": "independent_baseline", "risk": "low"}
        self.assertEqual(workflow_transition(state, {"kind": "verification", "passed": False})["phase"], "tester")
        self.assertEqual(workflow_transition(state, {"kind": "verification", "passed": False, "frozen": True})["phase"], "await_human")

    def test_risk_is_monotonic_and_critical_paths_require_full_graph(self):
        decision = workflow_transition({"phase": "architect", "risk": "medium"}, {"kind": "risk", "risk": "low"})
        self.assertEqual(decision["risk"], "medium")
        decision = workflow_transition({"phase": "developer", "risk": "low"}, {"kind": "risk", "critical": True})
        self.assertEqual(decision["phase"], "test_design")
        self.assertEqual(workflow_transition(decision, {"kind": "advance"})["phase"], "chief_plan")

    def proof(self):
        revision = {"head": "b" * 40, "base": "a" * 40, "spec_hash": "owner-spec"}
        current = {**revision, "passed": True}
        return {"phase": "publish", "risk": "low", "revision": revision, "proofs": {
            "candidate": current, "independent": copy.deepcopy(current), "acceptance": {"passed": True},
            "reviews": {"reviewer": {**revision, "verdict": "ready", "acceptance_passed": True}},
            "ci": copy.deepcopy(current), "merge": {"sha": "c" * 40, "parents": [revision["base"], revision["head"]]},
            "postmerge": {**current, "head": "c" * 40, "complete": True}}}

    def test_each_release_stage_requires_its_own_current_evidence(self):
        for stage in ("candidate", "integration", "postmerge"):
            self.assertTrue(require_workflow_evidence(self.proof(), stage))
        for category in ("candidate", "independent", "ci", "postmerge"):
            for field in ("head", "base", "spec_hash", "passed"):
                state = self.proof(); state["proofs"][category][field] = "stale"
                with self.subTest(category=category, field=field), self.assertRaises(CoreError):
                    require_workflow_evidence(state, "postmerge")
        for field in ("head", "base", "spec_hash", "verdict", "acceptance_passed"):
            state = self.proof(); state["proofs"]["reviews"]["reviewer"][field] = "stale"
            with self.subTest(review=field), self.assertRaises(CoreError):
                require_workflow_evidence(state, "candidate")

    def test_model_review_or_green_merge_checks_do_not_replace_missing_execution(self):
        state = self.proof(); state["proofs"].pop("independent")
        with self.assertRaises(CoreError): require_workflow_evidence(state, "postmerge")
        state = self.proof(); state["proofs"]["merge"]["parents"].reverse()
        with self.assertRaises(CoreError): require_workflow_evidence(state, "postmerge")
        state = self.proof(); state["proofs"]["postmerge"]["complete"] = False
        with self.assertRaises(CoreError): require_workflow_evidence(state, "postmerge")
