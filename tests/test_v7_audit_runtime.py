from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from reference_runtime.conformance import run_human_resume
from reference_runtime.contracts import load_json
from reference_runtime.engine import AutonomousEngine
from reference_runtime.scenarios import build_request, load_scenario
from reference_runtime.schema_validation import validate_evidence_directory


ROOT = Path(__file__).resolve().parents[1]


class AuditRuntimeTests(unittest.TestCase):
    def _engine(self, directory: str) -> AutonomousEngine:
        return AutonomousEngine(
            ROOT,
            build_request(
                ROOT,
                "happy-path",
                load_json(ROOT / "examples" / "goal.example.json"),
            ),
            Path(directory),
        )

    def test_goal_evaluation_reports_success_condition_as_reasoning_context(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            value = engine._goal_evaluation()
            self.assertEqual(value["success_condition_semantics"], "reasoning_context")

    def test_candidate_audit_ref_survives_candidate_branch_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            engine.init_git()
            engine.git("checkout", "-b", "candidate-audit")
            path = engine.workspace / "src" / "reference_app" / "audit_marker.py"
            path.write_text("MARKER = True\n")
            engine.git("add", str(path.relative_to(engine.workspace)))
            engine.git("commit", "-m", "Candidate audit object")
            candidate_sha = engine.git("rev-parse", "HEAD")

            ref = engine._retain_candidate(candidate_sha, "EXAMPLE-001", 1)
            engine.git("checkout", "main")
            engine.git("branch", "-D", "candidate-audit")

            self.assertEqual(engine.git("rev-parse", ref), candidate_sha)

    def test_human_request_changes_revalidates_retry_preconditions(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = load_scenario(ROOT, "human-request-changes")
            summary, evidence = run_human_resume(ROOT, Path(directory), spec)
            self.assertIn(summary["status"], {"COMPLETED", "NEEDS_DECISION"})
            artifact = evidence / "retry-preconditions-example-001-attempt-02.json"
            self.assertTrue(artifact.is_file())
            value = json.loads(artifact.read_text())
            self.assertTrue(value["diagnostic_junit_passed"])
            self.assertTrue(value["regression_probes_passed"])
            self.assertTrue(value["negative_control_passed"])
            self.assertIn(artifact.name, validate_evidence_directory(ROOT, evidence))


if __name__ == "__main__":
    unittest.main()
