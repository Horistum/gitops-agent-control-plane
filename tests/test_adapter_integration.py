"""Public consumer contract exercised with real Git and external processes.

This is a test harness, not another controller or an AI provider. Role responses
and hosted check responses are explicit test doubles. Git identities, process
results, counterfactuals and post-merge observations are real local operations.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from control_plane_core import (
    CoreError, acceptance_contract, acceptance_evidence, completion_transition,
    context_checkpoint, context_files, context_view, evaluate_goal_conditions,
    evaluate_obligations, evaluate_predicates, evidence_status_valid, identity,
    next_attempt, next_phase, require_merge_identity, require_revision_identity,
    retirement, test_criteria, test_failure_kind, trusted_checks_pass,
    validate_goal_conditions, verification_transition,
)
from reference_runtime.adapters import LocalGitEffectAdapter, LocalVerificationAdapter
from reference_runtime.executor import LocalFixtureExecutor


class AdapterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "product"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Contract test")
        self.git("config", "user.email", "test@example.invalid")
        self.source = self.repo / "app.py"
        self.source.write_text("print('old')\n")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        self.effect = LocalGitEffectAdapter(self.git)
        self.verifier = LocalVerificationAdapter(LocalFixtureExecutor(5))
        self.spec = identity({"stdout": "new\n"})
        self.bindings = [{"criterion_id": "AC-1", "test_id": "cli-output", "mode": "new_behavior"}]
        self.predicates = [{"id": "exit", "op": "exit_code", "expected": 0},
                           {"id": "output", "op": "stdout_equals", "expected": "new\n"}]

    def git(self, *args, capture=True, check=True):
        result = subprocess.run(["git", *args], cwd=self.repo, text=True,
                                capture_output=True, check=check)
        return result.stdout.strip()

    def candidate(self, text="new"):
        self.git("checkout", "-B", "candidate", self.base)
        self.source.write_text("print(" + repr(text) + ")\n")
        self.git("add", ".")
        self.git("commit", "-m", "candidate")
        return self.git("rev-parse", "HEAD")

    def observe(self, revision):
        # Detached exact revision; product cannot supply authoritative observations.
        self.git("checkout", "--detach", revision)
        result = self.verifier.run([sys.executable, "-S", "app.py"], self.repo)
        observed = {"exit_code": result.returncode, "stdout": result.stdout}
        passed = evaluate_predicates(self.predicates, observed)["passed"]
        return {"head": self.git("rev-parse", "HEAD"), "base": self.base,
                "spec_hash": self.spec, "passed": passed,
                "junit": {"executed_identities": ["cli-output"],
                          "failed_identities": [] if passed else ["cli-output"],
                          "error_identities": []}}, observed

    def test_high_graph_reaches_real_counterfactual_merge_and_goal_completion(self):
        head = self.candidate()
        criteria = acceptance_contract(
            [{"id": "AC-1", "text": "New CLI result"}, {"id": "AC-2", "text": "Delivered"}],
            [{"criterion_id": "AC-1", "kind": "behavior", "paths": [], "targets": []},
             {"criterion_id": "AC-2", "kind": "delivery", "paths": [], "targets": []}])
        self.assertEqual([r["id"] for r in test_criteria(criteria)], ["AC-1"])
        self.assertTrue(evidence_status_valid(criteria[1], {"status": "deferred", "evidence": "postmerge"}))
        phase, visited, merge, completed = "architect", [], None, []
        for _ in range(24):
            visited.append(phase)
            if phase == "independent_baseline":
                baseline, _ = self.observe(self.base)
                self.assertFalse(baseline["passed"])
            elif phase == "independent_verify":
                candidate, _ = self.observe(head)
                evidence = acceptance_evidence(["AC-1"], self.bindings, baseline, candidate)
                self.assertTrue(evidence["passed"])
                obligations = evaluate_obligations(criteria, {"AC-1": evidence["passed"]}, stage="candidate")
                self.assertTrue(obligations["passed"])
                self.assertFalse(obligations["complete"])
            elif phase == "merge":
                require_revision_identity({"candidate": head}, {"candidate": self.git("rev-parse", "candidate")})
                merge = self.effect.merge_exact(self.base, head, "deliver\n\nEffect-Id: integration-1")
                require_merge_identity(self.base, head, self.git("show", "-s", "--format=%P", merge).split())
            elif phase == "postmerge":
                receipt, observed = self.observe(merge)
                conditions = validate_goal_conditions([{"id": "G-1", "kind": "cli_case", "case": "output"}], ["ITEM"], ["output"])
                goals = evaluate_goal_conditions(conditions, {"cli_cases": {"output": evaluate_predicates(self.predicates, observed)["passed"]}})
                self.assertTrue(goals["passed"])
                obligations = evaluate_obligations(criteria, {"AC-1": receipt["passed"], "AC-2": True}, stage="postmerge")
                completed = completion_transition(["ITEM"], completed, "ITEM", merge_sha=merge,
                                                  verification_passed=obligations["complete"])["completed"]
            elif phase == "done":
                break
            phase = next_phase(phase, level="high", challenge=True)
        self.assertEqual(phase, "done")
        self.assertEqual(completed, ["ITEM"])
        self.assertTrue({"test_design", "chief_plan", "challenge_review", "architect_accept", "chief_accept"} <= set(visited))
        self.assertLess(visited.index("independent_baseline"), visited.index("independent_verify"))
        self.assertEqual(self.effect.find_trailer_effect("Effect-Id", "integration-1"), [merge])

    def test_real_failure_routes_repair_and_revision_scopes_persisted_context(self):
        broken = self.candidate("wrong")
        receipt, observed = self.observe(broken)
        target = verification_transition("independent_verify", receipt["passed"], failure_kind=test_failure_kind(receipt))
        self.assertEqual(target, "developer")
        kept, omitted = context_files(["app.py"], [], ["stale.py"], 1)
        self.assertEqual(omitted, ["stale.py"])
        notes = context_checkpoint(None, revision=broken, phase=target,
                                   summary="Observed output disagrees with approved specification",
                                   sources={kept[0]: {"sha256": identity(self.source.read_text())}},
                                   requests={}, facts=observed, turn_id=1)
        durable = self.root / "checkpoint.json"
        durable.write_text(json.dumps({target: notes}))
        restored = json.loads(durable.read_text())
        self.assertEqual(context_view(restored, target, broken), notes)
        self.assertEqual(context_view(restored, "reviewer", broken), {})
        next_id = next_attempt(1)
        fixed = self.candidate("new")
        self.assertEqual(context_view(restored, target, fixed), {})
        baseline, _ = self.observe(self.base)
        candidate, _ = self.observe(fixed)
        self.assertTrue(acceptance_evidence(["AC-1"], self.bindings, baseline, candidate)["passed"])
        archived = retirement({"id": "ITEM", "attempt": 1}, 1, [], "repaired")
        self.assertEqual(archived["next_attempt"], next_id)
        self.assertEqual(self.git("rev-parse", "main"), self.base)

    def test_stale_base_cas_and_missing_postmerge_observation_cannot_complete(self):
        head = self.candidate()
        self.git("checkout", "main")
        (self.repo / "other.txt").write_text("concurrent main change\n")
        self.git("add", ".")
        self.git("commit", "-m", "concurrent change")
        concurrent = self.git("rev-parse", "HEAD")
        with self.assertRaises(subprocess.CalledProcessError):
            self.effect.merge_exact(self.base, head, "stale effect")
        self.assertEqual(self.git("rev-parse", "main"), concurrent)
        with self.assertRaises(CoreError):
            completion_transition(["ITEM"], [], "ITEM", merge_sha=concurrent, verification_passed=False)

    def test_untrusted_or_failed_hosted_check_does_not_open_merge_stage(self):
        # Provider response test doubles: no claim of a live GitHub API check.
        required = [{"name": "build", "app_id": 15368}]
        for app, conclusion in ((1, "success"), (15368, "failure")):
            observed = [{"id": 1, "name": "build", "app_id": app,
                         "status": "completed", "conclusion": conclusion}]
            phase = verification_transition("ci", trusted_checks_pass(required, observed))
            self.assertEqual(phase, "await_human")
            self.assertEqual(self.git("rev-parse", "main"), self.base)
