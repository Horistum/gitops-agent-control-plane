from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from reference_runtime.contracts import (
    CORE_CONTRACT,
    REFERENCE_CONTRACT,
    RUNTIME_PROFILE,
    VERIFICATION_PROFILE,
    load_json,
    validate_authority_model,
    validate_contract_set,
    validate_goal,
    validate_goal_against_roadmap,
    validate_policy,
    validate_release_state,
    validate_roadmap,
    validate_role_protocols,
)
from reference_runtime.engine import AutonomousEngine
from reference_runtime.scenarios import build_request
from reference_runtime.schema_validation import ARTIFACT_SCHEMA_PATTERNS

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "examples" / "minimal-product"


class ContractDecompositionTests(unittest.TestCase):
    def test_contract_set_separates_core_verification_and_runtime(self):
        value = load_json(ROOT / "config" / "contract-set.json")
        validate_contract_set(value)
        self.assertEqual(value["reference_contract"], REFERENCE_CONTRACT)
        self.assertEqual(value["core_contract"], CORE_CONTRACT)
        self.assertEqual(value["verification_profile"], VERIFICATION_PROFILE)
        self.assertEqual(value["runtime_profile"], RUNTIME_PROFILE)

    def test_goal_explicitly_classifies_machine_and_context_fields(self):
        goal = load_json(ROOT / "examples" / "goal.example.json")
        validate_goal(goal)
        self.assertEqual(goal["field_semantics"]["objective"], "reasoning_context")
        self.assertEqual(goal["field_semantics"]["items"], "enforced_intent")
        self.assertEqual(goal["field_semantics"]["success_condition"], "verified_projection")

    def test_policy_bounds_goal_autonomy(self):
        policy = load_json(ROOT / "config" / "reference-policy.json")
        goal = load_json(ROOT / "examples" / "goal.example.json")
        validate_policy(policy)
        self.assertLessEqual(goal["autonomy"]["max_cycles"], policy["max_cycles"])
        self.assertLessEqual(
            goal["autonomy"]["max_attempts_per_item"],
            policy["max_attempts_per_item"],
        )


class AuthorityAndRoleProtocolTests(unittest.TestCase):
    def test_authority_model(self):
        model = load_json(PRODUCT / ".agent-control" / "authority-model.json")
        validate_authority_model(model)
        self.assertEqual(model["artifacts"]["roadmap.json"]["class"], "intent_authority")
        self.assertEqual(
            model["artifacts"]["release-state.json"]["mutation"],
            "controller-after-verified-effect",
        )
        self.assertEqual(
            model["artifacts"]["architecture.md"]["enforcement"],
            "reasoning-context",
        )

    def test_role_protocols_have_no_effect_power(self):
        value = load_json(ROOT / "config" / "role-protocols.json")
        validate_role_protocols(value)
        self.assertEqual(
            set(value["roles"]),
            {"discovery", "architect", "developer", "test-designer", "tester", "reviewer"},
        )
        self.assertTrue(all(row["effect_power"] == "none" for row in value["roles"].values()))

    def test_roadmap_rejects_duplicate_unknown_and_cyclic_dependencies(self):
        roadmap = load_json(PRODUCT / ".agent-control" / "roadmap.json")
        validate_roadmap(roadmap)

        duplicate = deepcopy(roadmap)
        duplicate["items"][1]["id"] = duplicate["items"][0]["id"]
        duplicate["items"][1]["dependencies"] = []
        with self.assertRaisesRegex(ValueError, "ids must be unique"):
            validate_roadmap(duplicate)

        unknown = deepcopy(roadmap)
        unknown["items"][1]["dependencies"] = ["MISSING"]
        with self.assertRaisesRegex(ValueError, "unknown dependencies"):
            validate_roadmap(unknown)

        cycle = deepcopy(roadmap)
        cycle["items"][0]["dependencies"] = ["EXAMPLE-002"]
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            validate_roadmap(cycle)

    def test_release_state_requires_verified_dependency_order(self):
        roadmap = load_json(PRODUCT / ".agent-control" / "roadmap.json")
        state = load_json(PRODUCT / ".agent-control" / "release-state.json")
        validate_release_state(state, roadmap)

        wrong_order = deepcopy(state)
        wrong_order["completed"] = ["EXAMPLE-002"]
        wrong_order["history"] = [{
            "item": "EXAMPLE-002",
            "verified_merge_sha": "a" * 40,
            "recorded_by": "controller",
        }]
        with self.assertRaisesRegex(ValueError, "before dependencies"):
            validate_release_state(wrong_order, roadmap)

        mismatched = deepcopy(state)
        mismatched["completed"] = ["EXAMPLE-001"]
        with self.assertRaisesRegex(ValueError, "history order"):
            validate_release_state(mismatched, roadmap)

    def test_goal_cannot_request_unknown_roadmap_item(self):
        goal = load_json(ROOT / "examples" / "goal.example.json")
        roadmap = load_json(PRODUCT / ".agent-control" / "roadmap.json")
        validate_goal_against_roadmap(goal, roadmap)
        bad = deepcopy(goal)
        bad["items"] = ["EXAMPLE-404"]
        with self.assertRaisesRegex(ValueError, "unknown roadmap items"):
            validate_goal_against_roadmap(bad, roadmap)

    def test_all_per_cycle_safety_archives_have_schema_routes(self):
        samples = (
            "test-baseline-example-001-cycle-01.json",
            "probe-baseline-example-001-cycle-01.json",
            "risk-decision-example-001-attempt-01.json",
            "merge-intent-example-001.json",
            "merge-evidence-example-001.json",
            "test-postmerge-example-001.json",
            "probe-postmerge-example-001.json",
            "postmerge-evidence-example-001.json",
        )
        for name in samples:
            self.assertTrue(
                any(pattern.fullmatch(name) for pattern, _ in ARTIFACT_SCHEMA_PATTERNS),
                name,
            )


class AutonomousSelectionTests(unittest.TestCase):
    def _engine(self, scenario: str, directory: str) -> AutonomousEngine:
        return AutonomousEngine(
            ROOT,
            build_request(ROOT, scenario, load_json(ROOT / "examples" / "goal.example.json")),
            Path(directory),
        )

    def test_dependency_selection_unlocks_second_item_only_after_release_state(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine("autonomous-two-item", directory)
            self.assertEqual([item["id"] for item in engine.eligible_items()], ["EXAMPLE-001"])
            path = engine.workspace / ".agent-control" / "release-state.json"
            state = json.loads(path.read_text())
            state["completed"] = ["EXAMPLE-001"]
            state["history"] = [{
                "item": "EXAMPLE-001",
                "verified_merge_sha": "a" * 40,
                "recorded_by": "controller",
            }]
            path.write_text(json.dumps(state))
            engine.authority = engine.load_authority()
            self.assertEqual([item["id"] for item in engine.eligible_items()], ["EXAMPLE-002"])

    def test_repair_catalog_has_two_attempts(self):
        request = build_request(
            ROOT,
            "repair-loop",
            load_json(ROOT / "examples" / "goal.example.json"),
        )
        self.assertEqual(len(request["work_catalog"]["EXAMPLE-001"]), 2)

    def test_runtime_installs_profile_adapters(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self._engine("autonomous-two-item", directory)
            self.assertEqual(engine.verification_adapter.profile, RUNTIME_PROFILE)
            self.assertEqual(engine.effect_adapter.profile, RUNTIME_PROFILE)


if __name__ == "__main__":
    unittest.main()
