from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from reference_runtime.contracts import load_json
from reference_runtime.engine import AutonomousEngine
from reference_runtime.scenarios import build_request
from reference_runtime.schema_validation import ARTIFACT_SCHEMAS

ROOT = Path(__file__).resolve().parents[1]


class PhaseRecoveryTests(unittest.TestCase):
    def _engine(self, directory: str) -> AutonomousEngine:
        goal = load_json(ROOT / "examples" / "goal.example.json")
        request = build_request(ROOT, "happy-path", goal)
        return AutonomousEngine(ROOT, request, Path(directory))

    def test_phase_recovery_evidence_has_schema_route(self):
        self.assertEqual(ARTIFACT_SCHEMAS["phase-recovery.json"], "phase-recovery.schema.json")

    def test_phase_recovery_scenarios_are_explicit(self):
        postmerge = load_json(ROOT / "examples" / "scenarios" / "postmerge-phase-crash-recovery.json")
        reconcile = load_json(ROOT / "examples" / "scenarios" / "reconcile-phase-crash-recovery.json")
        self.assertEqual(postmerge["fault_injection"], "after-merge-receipt-before-postmerge")
        self.assertEqual(reconcile["fault_injection"], "after-release-state-receipt-before-reconcile")
        self.assertEqual(postmerge["expected_status"], "COMPLETED")
        self.assertEqual(reconcile["expected_status"], "COMPLETED")

    def test_paused_cycle_can_be_completed_after_human_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            engine.state.update({"cycle": 1, "current_item": "EXAMPLE-001", "attempt": 1})
            engine._append_cycle(
                "EXAMPLE-001",
                [{"attempt": 1, "result": "NEEDS_DECISION"}],
                "NEEDS_DECISION",
            )
            engine._set_current_cycle_attempt_result("COMPLETED", create_if_missing=False)
            control = json.loads((engine.evidence / "control-loop.json").read_text())
            row = control["cycles"][0]
            self.assertEqual(row["result"], "COMPLETED")
            self.assertEqual(row["attempts"][0]["result"], "COMPLETED")

    def test_recovery_can_reconstruct_missing_cycle_row(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            engine.state.update({"cycle": 1, "current_item": "EXAMPLE-001", "attempt": 1})
            engine._set_current_cycle_attempt_result("COMPLETED", create_if_missing=True)
            control = json.loads((engine.evidence / "control-loop.json").read_text())
            self.assertEqual(control["cycles"], [{
                "cycle": 1,
                "item": "EXAMPLE-001",
                "attempts": [{"attempt": 1, "result": "COMPLETED"}],
                "result": "COMPLETED",
            }])


if __name__ == "__main__":
    unittest.main()
