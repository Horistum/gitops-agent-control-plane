"""Portable CI repair-authority vectors; no provider authentication or effects."""
import copy
import itertools
import unittest

from . import evaluate_ci_recovery, evaluate_trusted_checks


class CIRecoveryConformance(unittest.TestCase):
    required = [{"name": "build", "app_id": 15368}]

    @staticmethod
    def row(identity, conclusion="failure", status="completed"):
        return {"id": identity, "name": "build", "app_id": 15368,
                "status": status, "conclusion": conclusion}

    def check_all_orders(self, rows, status, action):
        expected = None
        for order in itertools.permutations(rows):
            supplied = list(order)
            before = copy.deepcopy(supplied)
            actual = evaluate_ci_recovery(self.required, supplied)
            self.assertEqual((actual["status"], actual["action"]), (status, action))
            self.assertEqual({key: actual[key] for key in ("status", "passed", "failed")},
                             evaluate_trusted_checks(self.required, supplied))
            self.assertEqual(supplied, before)
            if expected is not None:
                self.assertEqual(actual, expected)
            expected = actual
        return expected

    def test_old_failure_cannot_override_new_pending_success_or_cancelled(self):
        for conclusion, status, classification, action in (
                (None, "in_progress", "pending", "wait"),
                ("success", "completed", "success", "advance"),
                ("cancelled", "completed", "failure", "wait"),
                ("skipped", "completed", "failure", "wait"),
                ("neutral", "completed", "failure", "wait")):
            with self.subTest(conclusion=conclusion):
                result = self.check_all_orders([self.row(1), self.row(2, conclusion, status)], classification, action)
                self.assertEqual(result["repair_checks"], [])

    def test_conflicting_and_invalid_sets_stop_even_with_a_failure(self):
        self.check_all_orders([self.row(1), self.row(1, "success")], "conflict", "stop")
        self.check_all_orders([self.row(1), self.row(2, None)], "invalid", "stop")
        self.check_all_orders([self.row(1), {"name": "other", "app_id": "not-an-app"}], "invalid", "stop")

    def test_only_latest_trusted_definitive_failure_authorizes_repair(self):
        for conclusion in ("failure", "timed_out"):
            rows = [self.row(1), self.row(2, conclusion), {**self.row(99), "app_id": 999}]
            result = self.check_all_orders(rows, "failure", "repair")
            self.assertEqual(result["repair_checks"], [rows[1]])
            result["repair_checks"][0]["conclusion"] = "changed"
            self.assertEqual(rows[1]["conclusion"], conclusion)

    def test_missing_observation_waits_and_empty_policy_stops(self):
        self.assertEqual(evaluate_ci_recovery(self.required, [])["action"], "wait")
        self.assertEqual(evaluate_ci_recovery([], [])["action"], "stop")
