"""Executable portable contract vectors. Both runtime profiles run these bytes."""
import unittest

from . import (CoreError, completion_transition, goal_projection, merge_authority,
               path_allowed, require_merge_identity, require_revision_identity,
               trusted_checks_pass)


class CoreConformance(unittest.TestCase):
    def test_dependency_ready_selection_and_progress(self):
        items = [{"id": "A", "dependencies": [], "ready": True},
                 {"id": "B", "dependencies": ["A"], "ready": True}]
        before = goal_projection(["A", "B"], [], items)
        self.assertEqual(before["eligible_items"], ["A"])
        self.assertEqual(before["blocked_dependencies"], {"B": ["A"]})
        after = goal_projection(["A", "B"], ["A"], items)
        self.assertEqual(after["eligible_items"], ["B"])
        self.assertFalse(after["satisfied"])
        self.assertTrue(goal_projection(["A", "B"], ["A", "B"], items)["satisfied"])

    def test_dependency_cannot_expand_scope(self):
        items = [{"id": "A", "dependencies": [], "ready": True},
                 {"id": "B", "dependencies": ["A"], "ready": True}]
        result = goal_projection(["B"], [], items)
        self.assertEqual(result["eligible_items"], [])
        self.assertFalse(result["satisfied"])

    def test_unready_item_is_not_selected_and_prose_is_not_completion(self):
        result = goal_projection(["A"], [], [{"id": "A", "dependencies": [], "ready": False}])
        self.assertEqual(result["eligible_items"], [])
        self.assertEqual(result["unavailable_items"], ["A"])
        self.assertEqual(result["success_condition_semantics"], "reasoning_context")
        self.assertFalse(result["satisfied"])

    def test_completion_only_projection_cannot_select_work(self):
        self.assertEqual(goal_projection(["A"], [])["eligible_items"], [])

    def test_graph_rejects_unknown_duplicate_cycle_and_ambiguous_case(self):
        bad = [
            [{"id": "A", "dependencies": ["missing"], "ready": True}],
            [{"id": "A", "dependencies": ["A"], "ready": True}],
            [{"id": "A", "dependencies": [], "ready": True}] * 2,
            [{"id": "A", "dependencies": [], "ready": True}, {"id": "a", "dependencies": [], "ready": True}],
            [{"id": "A", "dependencies": [], "ready": "true"}],
        ]
        for items in bad:
            with self.subTest(items=items), self.assertRaises(CoreError):
                goal_projection(["A"], [], items)

    def test_empty_or_unbounded_goal_is_not_success(self):
        for requested in ([], ["A"] * 257, ["A", "a"]):
            with self.subTest(requested=requested), self.assertRaises(CoreError):
                goal_projection(requested, [])

    def test_hard_risk_ceiling_cannot_be_approved(self):
        decision = merge_authority("high", risk_ceiling="medium", auto_merge_ceiling="medium")
        self.assertTrue(decision["blocked"])
        self.assertFalse(decision["requires_approval"])
        self.assertFalse(decision["auto_merge_allowed"])

    def test_risk_auto_and_human_authority_matrix(self):
        self.assertTrue(merge_authority("low", risk_ceiling="medium", auto_merge_ceiling="low")["auto_merge_allowed"])
        for kwargs in ({"risk": "medium", "auto_merge_ceiling": "low"},
                       {"risk": "low", "auto_merge_ceiling": "none"},
                       {"risk": "low", "auto_merge_ceiling": "medium", "critical": True},
                       {"risk": "high", "auto_merge_ceiling": "high"}):
            with self.subTest(kwargs=kwargs):
                result = merge_authority(**kwargs, risk_ceiling="high")
                self.assertTrue(result["requires_approval"])
                self.assertFalse(result["auto_merge_allowed"])

    def test_unknown_risk_never_defaults_to_low(self):
        with self.assertRaises(CoreError):
            merge_authority("unknown", risk_ceiling="high", auto_merge_ceiling="medium")

    def test_proposal_write_envelope(self):
        self.assertTrue(path_allowed("src/a.py", ["src/**"]))
        for path in ("src/../policy", "src//x", "/src/x", "src/.git/config", "src/./x", "src/x\\y", "src/x\x00"):
            with self.subTest(path=path):
                self.assertFalse(path_allowed(path, ["**"]))
        self.assertFalse(path_allowed("src/api/x", ["src/**"], ["src/api/**"]))
        self.assertFalse(path_allowed("src/a.py", []))
        self.assertFalse(path_allowed("src/a.py", ["src/**"], forbidden=["src/a.py"]))

    def test_merge_identity_requires_both_exact_parents(self):
        require_merge_identity("a" * 40, "b" * 40, ["a" * 40, "b" * 40])
        for parents in (["c" * 40, "b" * 40], ["a" * 40, "c" * 40], ["a" * 40], [], ["a" * 40, "b" * 40, "c" * 40]):
            with self.subTest(parents=parents), self.assertRaises(CoreError):
                require_merge_identity("a" * 40, "b" * 40, parents)
        with self.assertRaises(CoreError):
            require_revision_identity({"head": "a" * 40}, {})

    def test_latest_trusted_check_and_missing_checks_fail_closed(self):
        required = [{"name": "build", "app_id": 1}]
        good = {"id": 1, "name": "build", "app_id": 1, "status": "completed", "conclusion": "success"}
        self.assertTrue(trusted_checks_pass(required, [good]))
        for rows in ([], [{**good, "app_id": 2}], [good, {**good, "id": 2, "conclusion": "failure"}],
                     [good, {**good, "conclusion": "failure"}], [{**good, "status": "queued"}]):
            with self.subTest(rows=rows):
                self.assertFalse(trusted_checks_pass(required, rows))
        self.assertFalse(trusted_checks_pass([], [good]))
        self.assertFalse(trusted_checks_pass(required * 2, [good]))

    def test_completion_is_verified_idempotent_and_scoped(self):
        first = completion_transition(["A", "B"], [], "A", merge_sha="a" * 40, verification_passed=True)
        again = completion_transition(["A", "B"], first["completed"], "A", merge_sha="a" * 40, verification_passed=True)
        self.assertEqual(first, again)
        for item, passed, merge in (("A", False, "a" * 40), ("X", True, "a" * 40), ("A", True, "main")):
            with self.subTest(item=item, passed=passed), self.assertRaises(CoreError):
                completion_transition(["A"], [], item, merge_sha=merge, verification_passed=passed)


if __name__ == "__main__":
    unittest.main()
