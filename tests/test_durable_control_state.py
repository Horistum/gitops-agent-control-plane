from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from reference_runtime.contracts import load_json
from reference_runtime.engine import AutonomousEngine
from reference_runtime.scenarios import build_request
from reference_runtime.schema_validation import ARTIFACT_SCHEMAS, ARTIFACT_SCHEMA_PATTERNS

ROOT = Path(__file__).resolve().parents[1]


class DurableControlStateTests(unittest.TestCase):
    def _engine(self, directory: str) -> AutonomousEngine:
        goal = load_json(ROOT / "examples" / "goal.example.json")
        request = build_request(ROOT, "happy-path", goal)
        return AutonomousEngine(ROOT, request, Path(directory))

    def test_release_state_effect_intent_is_persisted_before_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            base_sha = engine.init_git()
            engine.state["base_sha"] = base_sha
            selected = engine.authority["roadmap"]["items"][0]
            effect = engine._prepare_control_state_effect(selected, "a" * 40)
            self.assertEqual(effect["effect"], "control-state")
            self.assertEqual(engine.state["phase"], "CONTROL_STATE_PENDING")
            self.assertEqual(engine.state["pending_effect"]["request_hash"], effect["request_hash"])
            self.assertTrue((engine.evidence / "control-state-intent.json").is_file())
            release = load_json(engine.workspace / ".agent-control" / "release-state.json")
            self.assertNotIn("EXAMPLE-001", release["completed"])

    def test_control_state_recovery_artifacts_have_schema_routes(self):
        self.assertEqual(
            ARTIFACT_SCHEMAS["control-state-intent.json"],
            "control-state-intent.schema.json",
        )
        self.assertEqual(
            ARTIFACT_SCHEMAS["control-state-recovery.json"],
            "control-state-recovery.schema.json",
        )
        self.assertTrue(any(
            pattern.fullmatch("control-state-intent-example-001.json")
            for pattern, _ in ARTIFACT_SCHEMA_PATTERNS
        ))

    def test_release_state_crash_recovery_scenario_is_mandatory_fixture(self):
        scenario = load_json(ROOT / "examples" / "scenarios" / "release-state-crash-recovery.json")
        self.assertEqual(scenario["fault_injection"], "after-release-state-effect-before-receipt")
        self.assertEqual(scenario["expected_status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
