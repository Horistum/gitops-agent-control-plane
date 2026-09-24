"""Dependency IDs have their own name without changing the operational contract."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from agent_runtime import contracts
from control_plane_core import CoreError, goal_projection
from control_plane_core.schema import SchemaValidationError, validate_instance
from runtime_support import goal, policy


class DependencyContractTests(unittest.TestCase):
    def dependency_schema(self):
        return contracts.GOAL_SCHEMA["properties"]["items"]["items"]["properties"]["dependencies"]

    def test_dependencies_use_an_independent_schema_not_path_authority(self):
        properties = contracts.GOAL_SCHEMA["properties"]["items"]["items"]["properties"]
        self.assertIs(self.dependency_schema(), contracts.DEPENDENCY_IDS)
        self.assertIsNot(contracts.DEPENDENCY_IDS, contracts.PATHS)
        self.assertIsNot(contracts.DEPENDENCY_IDS["items"], contracts.PATHS["items"])
        self.assertIs(properties["context"], contracts.PATHS)
        self.assertIs(contracts.CRITERION["properties"]["paths"], contracts.PATHS)

    def test_future_path_schema_changes_do_not_change_dependency_ids(self):
        before = deepcopy(self.dependency_schema())
        with patch.dict(contracts.PATHS, maxItems=1), \
             patch.dict(contracts.PATHS["items"], maxLength=10):
            self.assertEqual(self.dependency_schema(), before)
            validate_instance(["A" * 128, "B" * 128], self.dependency_schema())

    def test_legacy_wire_shape_is_preserved(self):
        # The outer schema stays compatible; core validation owns ID semantics.
        self.assertEqual(self.dependency_schema(), {
            "type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 500},
            "minItems": 0, "maxItems": 128,
        })

    def test_wire_bounds_remain_unchanged(self):
        for values in ([], ["A"], ["A" * 128], ["A" * 129], ["A" * 500], ["A"] * 128):
            with self.subTest(values=values):
                validate_instance(values, self.dependency_schema())
        for values in ([""], ["A" * 501], ["A"] * 129, [None], [1], [True], "TASK-1", {}):
            with self.subTest(values=values), self.assertRaises(SchemaValidationError):
                validate_instance(values, self.dependency_schema())

    def test_valid_dependencies_still_control_eligibility_without_mutation(self):
        configuration = policy(Path("/tmp/dependency-contract-product"))
        request = goal(two=True)
        original = deepcopy((configuration, request))
        contracts.validate_configuration(configuration, request)
        ids = [item["id"] for item in request["items"]]
        first = goal_projection(ids, [], request["items"])
        self.assertEqual(first["eligible_items"], ["TASK-1"])
        self.assertEqual(first["blocked_dependencies"], {"TASK-2": ["TASK-1"]})
        second = goal_projection(ids, ["TASK-1"], request["items"])
        self.assertEqual(second["eligible_items"], ["TASK-2"])
        self.assertEqual((configuration, request), original)

    def test_core_still_rejects_invalid_dependency_identities_and_graphs(self):
        cases = (
            ([], ["UNKNOWN"], "Unknown dependency"),
            ([], ["src/service.py"], "invalid item identity"),
            ([], ["A" * 129], "invalid item identity"),
            ([], ["TASK-1", "TASK-1"], "duplicate item identities"),
            ([], ["TASK-1", "task-1"], "duplicate item identities"),
            ([], ["TASK-2"], "dependency cycle"),
            (["TASK-2"], ["TASK-1"], "dependency cycle"),
        )
        for first, second, message in cases:
            with self.subTest(first=first, second=second):
                request = goal(two=True)
                request["items"][0]["dependencies"] = first
                request["items"][1]["dependencies"] = second
                # These are structurally valid strings, not valid dependency graphs.
                validate_instance(request, contracts.GOAL_SCHEMA)
                with self.assertRaisesRegex(CoreError, message):
                    contracts.validate_configuration(policy(Path("/tmp/dependency-contract-product")), request)


if __name__ == "__main__":
    unittest.main()
