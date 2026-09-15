from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from reference_runtime.base import PolicyConfigurationError
from reference_runtime.contracts import load_json, validate_role_protocols
from reference_runtime.engine import AutonomousEngine
from reference_runtime.scenarios import build_request, load_scenario

ROOT = Path(__file__).resolve().parents[1]


class HumanIdentityAndAuthorityTests(unittest.TestCase):
    def _engine(self, directory: str) -> AutonomousEngine:
        return AutonomousEngine(
            ROOT,
            build_request(
                ROOT,
                "autonomous-two-item",
                load_json(ROOT / "examples" / "goal.example.json"),
            ),
            Path(directory),
        )

    def test_human_approve_after_tamper_is_mandatory_scenario(self):
        spec = load_scenario(ROOT, "human-approve-after-tamper")
        self.assertEqual(spec["expected_status"], "BLOCKED_POLICY")
        self.assertEqual(spec["human_decision"], "approve")
        self.assertIs(spec["tamper_candidate_before_decision"], True)

    def test_role_protocol_write_power_is_live_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            protocols = copy.deepcopy(engine.role_protocols)
            protocols["roles"]["developer"]["product_write_power"] = "tester_allowed_paths"
            validate_role_protocols(protocols)
            engine.role_protocols = protocols

            src_ok, _ = engine.check_proposal(
                [{"path": "src/reference_app/service.py", "content": "x=1\n", "reason": "test"}],
                actor="developer",
            )
            test_ok, decisions = engine.check_proposal(
                [{"path": "tests/test_acceptance_dynamic.py", "content": "x=1\n", "reason": "test"}],
                actor="developer",
            )
            self.assertFalse(src_ok)
            self.assertTrue(test_ok)
            self.assertEqual(decisions[0]["role_protocol"], "developer")

    def test_authority_model_controls_controller_mutation_power(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine(directory)
            model = copy.deepcopy(engine.authority_model)
            model["artifacts"]["release-state.json"]["mutation"] = "product-owner"
            engine.authority_model = model
            selected = engine.authority["roadmap"]["items"][0]
            with self.assertRaisesRegex(PolicyConfigurationError, "lacks declared mutation authority"):
                engine._prepare_control_state_effect(selected, "a" * 40)

    def test_human_decision_schema_requires_observed_identity_fields(self):
        schema = json.loads((ROOT / "schemas" / "human-decision.schema.json").read_text())
        required = set(schema["required"])
        self.assertIn("observed_candidate_sha", required)
        self.assertIn("candidate_identity_matches", required)

    def test_merge_evidence_requires_actual_parent_identity(self):
        schema = json.loads((ROOT / "schemas" / "merge-evidence.schema.json").read_text())
        required = set(schema["required"])
        self.assertTrue(
            {"base_sha", "actual_first_parent_sha", "actual_second_parent_sha", "candidate_identity_matches"}
            <= required
        )


if __name__ == "__main__":
    unittest.main()
