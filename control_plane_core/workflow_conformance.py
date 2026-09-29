"""Portable aggregate contract; run unchanged by every production consumer."""
import copy
from contextlib import contextmanager
import sys
import unittest
from . import CoreError, workflow_transition, require_workflow_evidence, acceptance_contract, refine_acceptance
from .authorization import candidate_authorization, work_authorization


@contextmanager
def capture_workflow_trace():
    """Observe actual adapter calls without asking the adapter to report its path."""
    trace, previous = [], sys.getprofile()
    def observe(frame, event, value):
        if previous:
            previous(frame, event, value)
        if event == "return" and frame.f_code is workflow_transition.__code__ and isinstance(value, dict):
            if frame.f_locals["event"]["kind"] in {"advance", "verification"}:
                trace.append([frame.f_locals["state"]["phase"], value["phase"]])
    sys.setprofile(observe)
    try:
        yield trace
    finally:
        sys.setprofile(previous)


def require_delivery_trace(trace, *, challenge=False, cycles=1):
    phases = ["baseline", "architect", "test_design", "chief_plan", "developer", "verify", "tester",
              "independent_baseline", "independent_verify", "reviewer"]
    phases += (["challenge_review"] if challenge else [])
    phases += ["architect_accept", "chief_accept", "publish", "ci", "merge", "postmerge", "done"]
    expected = [[a, b] for a, b in zip(phases, phases[1:])] * cycles
    if trace != expected:
        raise AssertionError("Actual adapter workflow differs from the shared delivery contract: " + repr(trace))


class WorkflowConformance(unittest.TestCase):
    def test_owner_authority_separates_stable_work_from_exact_candidate(self):
        task = {"id":"WORK-1", "attempt":1, "head":"a"*40, "base":"b"*40,
                "spec_hash":"spec", "risk":"high", "plan":{"steps":["Accepted plan"]},
                "scenarios":[{"id":"TS-1"}], "working_files":["src/a.py"]}
        inputs = {"policy":"policy", "goal":"goal", "critical_paths":["src/a.py"]}
        work = work_authorization(task, **inputs)
        merge = candidate_authorization(task, **inputs)
        changed = dict(task, head="c"*40)
        self.assertEqual(work, work_authorization(changed, **inputs))
        self.assertNotEqual(merge, candidate_authorization(changed, **inputs))
        self.assertNotEqual(work, merge)
        for key, value in {"attempt":2, "base":"d"*40, "spec_hash":"other", "risk":"medium",
                           "plan":{"steps":["New plan"]}, "scenarios":[], "working_files":[]}.items():
            with self.subTest(field=key):
                self.assertNotEqual(work, work_authorization(dict(task, **{key:value}), **inputs))

    def test_only_planning_repairs_revoke_work_authority(self):
        state = {"phase":"reviewer", "risk":"high", "completed":["architect", "test_design", "chief_plan"]}
        for target in ("developer", "tester", "architect", "test_design"):
            decision = workflow_transition(state, {"kind":"repair", "target":target})
            self.assertIn("approval", decision["invalidated"])
            self.assertEqual("work_authorization" in decision["invalidated"], target in {"architect", "test_design"})
        self.assertIn("work_authorization", workflow_transition(state, {"kind":"base_changed"})["invalidated"])

    def test_model_refinement_preserves_owner_criteria_and_keeps_additional_handoff_obligations(self):
        owner = acceptance_contract([{"id": "AC-01", "text": "Deterministic system identity"}])
        proposed = acceptance_contract([{"id": "AC-01", "text": "Deterministic system identity"},
            {"id": "AC-02", "text": "Verify exact predecessor handoff"}], [
            {"criterion_id": "AC-01", "kind": "documentation", "paths": ["README.md"], "targets": []},
            {"criterion_id": "AC-02", "kind": "behavior", "paths": [], "targets": []}])
        combined = refine_acceptance(owner, proposed)
        self.assertEqual(combined[0], owner[0])
        self.assertEqual(combined[1]["id"], "PLAN-02")
        self.assertEqual(combined[1]["text"], proposed[1]["text"])
        self.assertEqual(combined[1]["kind"], "behavior")
    def test_late_escalation_inserts_missing_plan_gates_and_invalidates_release_authority(self):
        state = {"phase": "reviewer", "risk": "low", "completed": ["architect", "developer", "tester"]}
        decision = workflow_transition(state, {"kind": "risk", "risk": "high"})
        self.assertEqual(decision["phase"], "test_design")
        self.assertEqual(decision["return_phase"], "verify")
        self.assertEqual(set(decision["invalidated"]), {"candidate", "reviews", "ci", "approval", "work_authorization"})
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
