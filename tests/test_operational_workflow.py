"""Behavior of the real adapters at the shared workflow boundaries."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from agent_runtime.controller import Controller
from agent_runtime.actions import action
from agent_runtime.io import digest
from runtime_support import build_product, goal, policy, InProcessProvider


class WorkflowRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.product = self.root / "product"
        build_product(self.product)
        self.policy = policy(self.product); self.goal = goal()

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

    def test_low_risk_graph_skips_expensive_plan_reviews_but_executes_independent_tests(self):
        self.policy.update(adaptive_agent_graph=True, challenge=False)
        engine = self.start(); result = self.drive(engine)
        self.assertEqual(result["status"], "COMPLETED", result)
        phases = [row["phase"] for row in engine.state["history"]]
        self.assertNotIn("chief_plan", phases); self.assertNotIn("chief_accept", phases)
        self.assertIn("independent_baseline", phases); self.assertIn("independent_verify", phases)
        self.assertIn("reviewer", phases)
        self.assertEqual(result["head"], engine.repo.resolve("main"))

    def test_late_risk_reroutes_before_applying_model_edits_and_revalidates(self):
        self.policy.update(adaptive_agent_graph=True, challenge=False, auto_merge_ceiling="medium")
        self.goal["auto_merge_ceiling"] = "medium"
        def escalate(payload, value, _):
            if payload["phase"] == "developer": value["risk"] = "medium"
        engine = self.start(InProcessProvider(escalate))
        self.drive(engine, "developer"); original = engine.task["head"]
        self.assertEqual(engine.tick()["phase"], "test_design")
        self.assertEqual(engine.task["head"], original)
        result = self.drive(engine)
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertIn("architect_accept", engine.state["archive"][0]["completed_phases"])

    def test_document_only_runs_real_suite_without_fabricated_test_binding(self):
        self.goal["items"][0].update(context=["README.md"], acceptance=[
            {"id": "AC-1", "text": "Explain the existing interface", "kind": "documentation", "paths": ["README.md"], "targets": []}])
        def documents(payload, value, _):
            if payload["phase"] == "test_design": value["scenarios"] = []
            if payload["phase"] == "developer": value["edits"][0]["content"] = "value() returns a positive integer.\n"
            if payload["phase"] == "tester": value.update(edits=[], bindings=[])
        engine = self.start(InProcessProvider(documents)); result = self.drive(engine)
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertEqual(engine.state["archive"][0]["frozen_tests"]["bindings"], [])
        self.assertEqual(engine.repo.read(engine.state["base"], "app.py"), (self.product / "app.py").read_bytes())

    def test_base_refresh_replays_effect_and_invalidates_candidate_approval(self):
        self.goal = goal(approval=True)
        provider = InProcessProvider(); engine = self.start(provider)
        held = self.drive(engine); action(engine.root, "approve", held["approval"])
        engine = Controller(engine.root, reasoning=provider)
        base = engine.task["base"]
        moved = engine.repo.commit(base, [{"path": "other.py", "expected_sha256": "", "delete": False,
                                         "content": "# concurrent independent change\n"}], "concurrent",
                                  allowed=["*.py"], protected=[])
        engine.repo.text("update-ref", "refs/heads/main", moved, base)
        # Exercise persisted receipt replay after a hard process interruption.
        class Crash(BaseException): pass
        def crash(_):
            if engine.state["pending"]["kind"] == "refresh-base": raise Crash()
        engine.store.after_receipt = crash
        with self.assertRaises(Crash): engine.tick()
        engine = Controller(engine.root, reasoning=provider)
        result = self.drive(engine)
        self.assertEqual(result["status"], "NEEDS_DECISION", result)
        self.assertNotEqual(result["approval"], held["approval"])
        self.assertEqual(engine.task["base"], moved)
        self.assertEqual(engine.task["baseline"]["head"], moved)
        self.assertEqual(engine.task["candidate_evidence"]["base"], moved)
        action(engine.root, "approve", result["approval"])
        result = self.drive(Controller(engine.root, reasoning=provider))
        self.assertEqual(result["status"], "COMPLETED", result)

    def test_search_hydrates_hashed_excerpt_and_does_not_prime_independent_review(self):
        def retrieval(payload, value, _):
            if payload["phase"] == "architect" and not payload["task"].get("search_results"):
                value.update(verdict="need_context", requested_files=[], requested_searches=["Test product"])
        provider = InProcessProvider(retrieval); engine = self.start(provider)
        result = self.drive(engine)
        self.assertEqual(result["status"], "COMPLETED", result)
        calls = [p for p in provider.calls if p["phase"] == "architect"]
        excerpt = next(v for k, v in calls[1]["sources"].items() if k.startswith("README.md#L"))
        self.assertEqual(excerpt["sha256"], digest((self.product / "README.md").read_bytes()))
        self.assertIn("Test product", excerpt["content"])
        reviewer = next(p for p in provider.calls if p["phase"] == "reviewer")
        self.assertNotIn("role_results", reviewer["task"])
        self.assertEqual(reviewer["memory"], {})

    def test_architect_working_set_cannot_claim_a_test_path(self):
        def overreach(payload, value, _):
            if payload["phase"] == "architect":
                value["working_set"] = value["working_set"] + ["tests/test_extra.py"]
        engine = self.start(InProcessProvider(overreach))
        result = self.drive(engine)
        self.assertEqual(result["status"], "BLOCKED_POLICY", result)
        self.assertIn("Architect working set exceeds source authority", result["reason"])
        self.assertEqual(engine.task["working_set"], [])

    def test_stale_spec_review_is_rejected_at_publication_boundary(self):
        engine = self.start(); self.drive(engine, "publish")
        engine.task["role_results"]["reviewer"]["spec_hash"] = "another-spec"
        engine.store.save(); result = engine.tick()
        self.assertEqual(result["status"], "BLOCKED_POLICY", result)
        self.assertNotIn("merge_sha", engine.task)


if __name__ == "__main__": unittest.main()
