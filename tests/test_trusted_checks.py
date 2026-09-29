from __future__ import annotations

import copy
from itertools import permutations
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from control_plane_core import evaluate_trusted_checks, trusted_checks_pass
from agent_runtime.github import GitHub
from agent_runtime.io import Closed
from agent_runtime.lifecycle import lifecycle_step

REQUIRED = [{"name": "unit", "app_id": 1}]
GOOD = {"id": 42, "name": "unit", "app_id": 1, "status": "completed", "conclusion": "success"}
REVISION, BASE, CANDIDATE = "c" * 40, "a" * 40, "b" * 40


class TrustedCheckTests(unittest.TestCase):
    def assert_status(self, rows, status, required=None):
        required = REQUIRED if required is None else required
        before = copy.deepcopy((required, rows))
        value = evaluate_trusted_checks(required, rows)
        self.assertEqual(value, {"status": status, "passed": status == "success", "failed": status == "failure"})
        self.assertIs(trusted_checks_pass(required, rows), value["passed"])
        self.assertEqual((required, rows), before)

    def test_latest_required_provider_observation_and_strict_success(self):
        for rows, status in (
            ([GOOD], "success"), ([GOOD, dict(GOOD)], "success"),
            ([{**GOOD, "id": 41, "conclusion": "failure"}, GOOD], "success"),
            ([GOOD, {**GOOD, "id": 43, "status": "in_progress", "conclusion": None}], "pending"),
            ([{**GOOD, "app_id": 2}], "pending"), ([], "pending"),
            ([GOOD, {**GOOD, "app_id": 2, "conclusion": "failure"}], "success"),
            ([{**GOOD, "conclusion": "failure"}], "failure"),
            ([{**GOOD, "conclusion": "skipped"}], "failure"),
            ([{**GOOD, "conclusion": "neutral"}], "failure"),
            ([{**GOOD, "conclusion": None}], "invalid"),
        ):
            for order in permutations(rows):
                with self.subTest(rows=order):
                    self.assert_status(list(order), status)

    def test_conflicting_identity_is_detected_even_when_superseded_by_newer_success(self):
        for observations in (
            [GOOD, {**GOOD, "conclusion": "failure"}],
            [GOOD, {**GOOD, "conclusion": "failure"}, {**GOOD, "id": 43}],
            [GOOD, {**GOOD, "details": "conflicting observation"}],
        ):
            for order in permutations(observations):
                with self.subTest(rows=order):
                    self.assert_status(list(order), "conflict")

    def test_invalid_has_fixed_precedence_over_conflict_or_failure(self):
        for bad in ({**GOOD, "id": True}, {**GOOD, "status": None}, {**GOOD, "conclusion": None}):
            rows = [GOOD, {**GOOD, "conclusion": "failure"}, bad]
            for order in permutations(rows):
                self.assert_status(list(order), "invalid")
        for required in ([], REQUIRED * 2, [{"name": "unit", "app_id": True}], None):
            self.assertEqual(evaluate_trusted_checks(required, [GOOD])["status"], "invalid")
        for rows in ([None], [{**GOOD, "name": []}], [{**GOOD, "status": None}], None):
            self.assert_status(rows, "invalid")

    def test_confirmed_failure_can_precede_other_pending_required_checks(self):
        required = REQUIRED + [{"name": "integration", "app_id": 1}]
        self.assert_status([GOOD], "pending", required)
        self.assert_status([{**GOOD, "conclusion": "failure"}], "failure", required)

    def github(self, observations):
        rows = [{**value, "app": {"id": value["app_id"]}, "head_sha": REVISION}
                for value in observations]
        return GitHub({"repository": "example/project", "required_checks": REQUIRED}, "main",
                      transport=lambda *args: {"check_runs": copy.deepcopy(rows)})

    def test_conflict_stops_without_product_repair_for_either_order(self):
        for rows in permutations([GOOD, {**GOOD, "conclusion": "failure"}]):
            for phase in ("ci", "postmerge"):
                with self.subTest(order=rows, phase=phase):
                    github = self.github(rows)
                    result = github.checks(REVISION)
                    self.assertEqual((result["passed"], result["failed"], result["status"]), (False, False, "conflict"))
                    holds = []
                    engine = SimpleNamespace(
                        state={"pending": None},
                        task={"phase": phase, "risk": "low", "head": REVISION, "base": BASE,
                              **({"merge_sha": REVISION} if phase == "postmerge" else {})},
                        repo=SimpleNamespace(parents=lambda _: [BASE, REVISION]),
                        github=github, hold=lambda reason: holds.append(reason),
                    )
                    with patch("agent_runtime.lifecycle.candidate_gate", return_value=True), \
                         patch("agent_runtime.lifecycle.repair") as repair:
                        with self.assertRaisesRegex(Closed, "malformed or conflicting"):
                            lifecycle_step(engine)
                        repair.assert_not_called()
                    self.assertEqual(holds, [])
                    self.assertEqual(engine.task["phase"], phase)
                    self.assertEqual((engine.task["head"], engine.task["base"]), (REVISION, BASE))
                    self.assertEqual(engine.state, {"pending": None})

    def test_wrong_revision_is_rejected_and_malformed_app_cannot_pass(self):
        rows = [{"id": 42, "name": "unit", "head_sha": BASE, "app": {"id": 1},
                 "status": "completed", "conclusion": "success"}]
        github = GitHub({"repository": "example/project", "required_checks": REQUIRED}, "main",
                        transport=lambda *args: {"check_runs": rows})
        with self.assertRaises(Closed):
            github.checks(REVISION)
        rows[0].update(head_sha=REVISION, app=None)
        self.assertEqual(github.checks(REVISION)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
