"""Shared executable vectors for verification-evidence/v1."""
import copy
import unittest
from .decisions import CoreError, goal_projection, completion_transition
from .verification import (acceptance_evidence, evaluate_predicates, validate_bindings,
                           validate_goal_conditions, evaluate_goal_conditions, test_failure_kind)


class VerificationConformance(unittest.TestCase):
    def receipts(self):
        baseline = {"head": "a" * 40, "base": "b" * 40, "spec_hash": "spec", "passed": False,
                    "junit": {"executed_identities": ["Test:feature"], "failed_identities": ["Test:feature"]}}
        candidate = copy.deepcopy(baseline); candidate.update(head="c" * 40, passed=True)
        candidate["junit"]["failed_identities"] = []
        bindings = [{"criterion_id": "AC-01", "test_id": "Test:feature", "mode": "new_behavior"}]
        return baseline, candidate, bindings

    def test_counterfactual_requires_actual_failure_and_candidate_success(self):
        base, candidate, bindings = self.receipts()
        self.assertTrue(acceptance_evidence(["AC-01"], bindings, base, candidate)["passed"])
        base["junit"]["failed_identities"] = []
        self.assertFalse(acceptance_evidence(["AC-01"], bindings, base, candidate)["passed"])

    def test_regression_must_pass_on_both_revisions(self):
        base, candidate, bindings = self.receipts(); bindings[0]["mode"] = "regression"
        self.assertFalse(acceptance_evidence(["AC-01"], bindings, base, candidate)["passed"])
        base["junit"]["failed_identities"] = []
        self.assertTrue(acceptance_evidence(["AC-01"], bindings, base, candidate)["passed"])

    def test_skipped_missing_or_error_test_never_proves_new_behavior(self):
        for field, value in (("executed_identities", []), ("error_identities", ["Test:feature"])):
            base, candidate, bindings = self.receipts(); base["junit"][field] = value
            self.assertFalse(acceptance_evidence(["AC-01"], bindings, base, candidate)["passed"])

    def test_unrelated_baseline_failure_is_not_a_negative_control(self):
        base, candidate, bindings = self.receipts(); base["junit"]["failed_identities"].append("Other:broken")
        self.assertFalse(acceptance_evidence(["AC-01"], bindings, base, candidate)["passed"])

    def test_acceptance_coverage_and_revision_binding(self):
        base, candidate, bindings = self.receipts()
        with self.assertRaises(CoreError): validate_bindings(["AC-01", "AC-02"], bindings)
        candidate["base"] = "f" * 40
        with self.assertRaises(CoreError): acceptance_evidence(["AC-01"], bindings, base, candidate)

    def test_json_predicate_is_type_strict(self):
        p = [{"id": "typed", "op": "json_equals", "pointer": "/x", "expected": True}]
        self.assertTrue(evaluate_predicates(p, {"exit_code": 0, "stdout": '{"x":true}'})["passed"])
        for raw in ('{"x":1}', '{"x":false,"x":true}', '{"x":NaN}', 'REFERENCE_PROBE_RECEIPT={"passed":true}'):
            self.assertFalse(evaluate_predicates(p, {"exit_code": 0, "stdout": raw})["passed"])

    def test_exit_code_and_observed_output_both_required(self):
        p = [{"id": "code", "op": "exit_code", "expected": 2},
             {"id": "message", "op": "stdout_contains", "expected": "INVALID"}]
        self.assertTrue(evaluate_predicates(p, {"exit_code": 2, "stdout": "INVALID input"})["passed"])
        self.assertFalse(evaluate_predicates(p, {"exit_code": 0, "stdout": "INVALID input"})["passed"])

    def test_unknown_predicate_and_expression_are_rejected(self):
        with self.assertRaises(CoreError):
            evaluate_predicates([{"id": "unsafe", "op": "eval", "expected": "True"}], {"exit_code": 0, "stdout": ""})

    def test_typed_goal_requires_positive_observed_evidence(self):
        c = [{"id": "one", "kind": "cli_case", "case": "approved"},
             {"id": "two", "kind": "criterion", "item": "A", "criterion": "AC-01"}]
        validate_goal_conditions(c, ["A"], ["approved"])
        self.assertFalse(evaluate_goal_conditions(c, {})["passed"])
        self.assertTrue(evaluate_goal_conditions(c, {"cli_cases": {"approved": True}, "criteria": {"A": {"AC-01": True}}})["passed"])
        with self.assertRaises(CoreError): validate_goal_conditions(c, ["B"], ["approved"])

    def test_history_and_completion_beyond_graph_bound(self):
        done = ["OLD-" + str(i) for i in range(1000)]
        value = completion_transition(["NEW"], done, "NEW", merge_sha="a" * 40, verification_passed=True)
        self.assertTrue(value["goal"]["satisfied"])
        self.assertEqual(len(value["completed"]), 1001)

    def test_failure_routing_does_not_treat_assertions_as_test_defects(self):
        self.assertEqual(test_failure_kind({"junit": {"failed_identities": ["T:x"]}}), "product")
        self.assertEqual(test_failure_kind({"junit": {"error_identities": ["T:x"]}}), "ambiguous")
        self.assertEqual(test_failure_kind({"junit": {}}), "test_preparation")


if __name__ == "__main__": unittest.main()
