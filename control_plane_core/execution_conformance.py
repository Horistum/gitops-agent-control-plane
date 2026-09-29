"""Executable regression vectors shared byte-for-byte by both runtimes."""
import unittest

from .decisions import CoreError
from .execution import (context_checkpoint, context_files, context_view, next_phase,
                        recovery_actions, repair_target, retry_preconditions, model_call_action,
                        upgrade_boundary, verification_transition, next_attempt, technical_recovery)
from .acceptance import acceptance_contract, evaluate_obligations, evidence_status_valid, test_criteria


class ExecutionConformance(unittest.TestCase):
    def test_technical_recovery_deadline_bound_and_exhaustion_survive_projection(self):
        first = technical_recovery({}, now=100, failure_kind="transport", maximum=2, retry_after=120)
        self.assertEqual((first["action"], first["attempt"], first["delay"]), ("wait", 1, 120))
        saved = first["checkpoint"]
        self.assertEqual(technical_recovery(saved, now=219, maximum=2)["action"], "wait")
        self.assertEqual(technical_recovery(saved, now=220, maximum=2)["action"], "retry")
        second = technical_recovery(saved, now=220, failure_kind="not_dispatched", maximum=2)
        final = technical_recovery(second["checkpoint"], now=280, failure_kind="transport", maximum=2)
        self.assertEqual(final["action"], "exhausted")
        self.assertEqual(technical_recovery(final["checkpoint"], now=10000, maximum=2)["action"], "exhausted")
        self.assertEqual(saved["attempts"], 1)

    def test_unknown_policy_and_fenced_failures_never_grant_technical_retry(self):
        for kind in ("unknown_effect", "policy", "unclassified", "fenced"):
            result = technical_recovery({}, now=1, failure_kind=kind)
            self.assertEqual((result["action"], result["attempt"], result["retry"]), ("stop", 0, False))
        for malformed in (None, [], {"attempts": True}, {"attempts": -1},
                          {"next_attempt": False}, {"exhausted": "yes"}, {"failure_kind": []}):
            with self.subTest(malformed=malformed), self.assertRaises(CoreError):
                technical_recovery(malformed, now=1)
        for bounds in ({"now": True}, {"maximum": 0}, {"maximum": 21},
                       {"initial_delay": 0}, {"retry_after": -1}, {"failure_kind": []}):
            with self.subTest(bounds=bounds), self.assertRaises(CoreError):
                technical_recovery({}, **{"now": 1, **bounds})

    def test_manual_retry_requires_explicit_typed_technical_failure(self):
        task = dict(phase="await_human", hold_kind="FAILED", retryable=True, recovery_kind="transport")
        self.assertTrue(recovery_actions(task, {})["retry"])
        for changed in ({"recovery_kind": None}, {"retryable": False}, {"hold_kind": "BLOCKED_POLICY"},
                        {"pending": {"id": "unknown"}}, {"approvable": True},
                        {"agent_calls": 18}, {"context_rounds": 8}, {"failure_code": "PROTOCOL_LIMIT"}):
            with self.subTest(changed=changed):
                self.assertFalse(recovery_actions({**task, **changed}, {})["retry"])

    def test_model_dispatch_without_receipt_never_grants_automatic_retry(self):
        for state in ('dispatched', 'legacy_unknown'):
            self.assertEqual(model_call_action(receipt_available=False, dispatch_state=state), 'hold')
            self.assertEqual(model_call_action(receipt_available=True, dispatch_state=state), 'reuse')
        self.assertEqual(model_call_action(receipt_available=False, dispatch_state='not_started'), 'execute')
        with self.assertRaises(CoreError):
            model_call_action(receipt_available='yes', dispatch_state='not_started')

    def checkpoint(self, previous=None, **overrides):
        args = dict(revision="rev1", phase="architect", summary="first-match collision found",
                    sources={"catalog.py": {"sha256": "a", "text": "first match"}},
                    requests={"files": ["planner.py"]}, facts={})
        args.update(overrides)
        return context_checkpoint(previous, **args)

    def test_bounded_memory_survives_slices_and_does_not_mutate_previous(self):
        first = self.checkpoint()
        value = self.checkpoint(first, summary="planner invokes catalog", sources={"planner.py": {"sha256": "b"}})
        self.assertEqual(len(first["entries"]), 1)
        self.assertEqual(len(value["entries"]), 2)
        self.assertEqual(set(value["sources"]), {"catalog.py", "planner.py"})
        for i in range(20): value = self.checkpoint(value, summary=str(i))
        self.assertEqual(len(value["entries"]), 8)

    def test_context_provenance_preserves_partial_observation_without_source_text(self):
        import copy, hashlib
        source = {"part.py#L2-L4": {"path": "part.py", "sha256": "whole-file",
            "text": "ž\n", "excerpt": True, "truncated": True,
            "line_start": 2, "line_end": 2, "total_lines": 100}}
        original = copy.deepcopy(source)
        row = self.checkpoint(sources=source)["sources"]["part.py#L2-L4"]
        self.assertEqual(source, original)
        self.assertEqual(row["sha256"], "whole-file")
        self.assertEqual(row["observed_sha256"], hashlib.sha256("ž\n".encode()).hexdigest())
        self.assertEqual(row["observed_bytes"], len("ž\n".encode()))
        self.assertTrue(row["truncated"]); self.assertEqual(row["line_start"], 2)
        self.assertEqual(row["line_end"], 2); self.assertEqual(row["total_lines"], 100)
        self.assertNotIn("text", row)
        omitted = self.checkpoint(sources={"part.py": {"omitted": True, "bytes": 500,
            "git_blob": "blob", "content": "not delivered"}})["sources"]["part.py"]
        self.assertNotIn("observed_sha256", omitted)
        self.assertEqual(omitted["git_blob"], "blob")

    def test_reference_excerpt_and_observed_digest_are_independent_from_full_file_identity(self):
        source = {"part.py#L1-L2": {"sha256": "whole-file", "content": "a\n",
                  "excerpt": {"start": 1, "end": 1, "total_lines": 2}}}
        first = self.checkpoint(sources=source)
        source["part.py#L1-L2"]["excerpt"]["end"] = 2
        source["part.py#L1-L2"]["content"] = "a\nb\n"
        second = self.checkpoint(first, sources=source)
        a = first["sources"]["part.py#L1-L2"]; b = second["sources"]["part.py#L1-L2"]
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertNotEqual(a["observed_sha256"], b["observed_sha256"])
        self.assertEqual(a["excerpt"]["end"], 1)
        self.assertEqual(b["observed_bytes"], 4)
        retained = self.checkpoint(second, sources={})
        retained["sources"]["part.py#L1-L2"]["excerpt"]["end"] = 99
        self.assertEqual(second["sources"]["part.py#L1-L2"]["excerpt"]["end"], 2)

    def test_revision_and_role_boundaries_never_import_stale_or_correlated_notes(self):
        value = self.checkpoint()
        self.assertEqual(context_view({"architect": value}, "reviewer", "rev1"), {})
        self.assertEqual(context_view({"architect": value}, "architect", "rev2"), {})
        fresh = self.checkpoint(value, revision="rev2", sources={})
        self.assertEqual(fresh["sources"], {})
        self.assertEqual(len(fresh["entries"]), 1)

    def test_replay_of_same_durable_turn_does_not_count_as_new_failure(self):
        value = self.checkpoint(turn_id=3)
        self.assertEqual(self.checkpoint(value, turn_id=3), value)
        repeated = self.checkpoint(value, turn_id=4)
        self.assertEqual(repeated["repeats"], 1)
        progressed = self.checkpoint(repeated, sources={"new.py": {"sha256": "new"}}, turn_id=5)
        self.assertEqual(progressed["repeats"], 0)

    def test_fresh_requests_precede_retained_files_without_exceeding_bound(self):
        kept, omitted = context_files(["authority"], ["caller"], ["catalog", "registry"], 3)
        self.assertEqual(kept, ["authority", "caller", "catalog"])
        self.assertEqual(omitted, ["registry"])
        with self.assertRaises(CoreError): context_files(["a", "b"], [], [], 1)

    def test_invalid_context_limits_cannot_disable_retention_bounds(self):
        for value in (0, -1, True, 1.5):
            for limit in ("max_entries", "max_sources"):
                with self.subTest(limit=limit, value=value), self.assertRaises(CoreError):
                    self.checkpoint(**{limit: value})
        for value in (-1, True, 1.5):
            with self.subTest(limit=value), self.assertRaises(CoreError):
                context_files([], ["a"], [], value)
        self.assertEqual(context_files([], ["a"], [], 0), ([], ["a"]))

    def test_failure_ownership_does_not_start_implementation_before_design(self):
        finding = [{"kind": "testing", "severity": "medium"}]
        self.assertEqual(repair_target("test_design", "fix", finding), "test_design")
        self.assertEqual(repair_target("chief_plan", "fix", finding), "test_design")
        self.assertEqual(repair_target("architect", "fix", []), "architect")
        self.assertEqual(repair_target("reviewer", "fix", finding), "developer")
        self.assertEqual(repair_target("tester", "fix", finding), "tester")

    def test_exhausted_retry_is_not_advertised_and_replan_limit_is_real(self):
        task = dict(phase="await_human", hold_kind="FAILED", retryable=True, context_rounds=9)
        self.assertEqual(recovery_actions(task, {"max_context_rounds": 8}), {"retry": False, "replan": True})
        task["owner_replans"] = 2
        self.assertFalse(recovery_actions(task, {})["replan"])
        task.update(context_rounds=0, hold_kind="NEEDS_DECISION", approvable=True)
        self.assertFalse(recovery_actions(task, {})["retry"])

    def test_ready_routes_follow_risk_and_failed_assertions_preserve_tester(self):
        self.assertEqual(next_phase("architect", level="low"), "developer")
        self.assertEqual(next_phase("architect", level="medium"), "test_design")
        self.assertEqual(next_phase("test_design", level="high"), "chief_plan")
        self.assertEqual(verification_transition("independent_verify", False), "developer")
        self.assertEqual(verification_transition("independent_verify", False, failure_kind="ambiguous"), "await_human")
        self.assertEqual(verification_transition("postmerge", False), "await_human")
        with self.assertRaises(CoreError): verification_transition("postmerge", "true")

    def test_complete_graphs_execute_counterfactual_before_independent_candidate(self):
        visited = set()
        for level in ("low", "medium", "high"):
            for challenge in (False, True):
                with self.subTest(level=level, challenge=challenge):
                    phase, path = "architect", []
                    while phase != "done":
                        self.assertNotIn(phase, path, "Execution graph must terminate")
                        path.append(phase)
                        phase = next_phase(phase, level=level, challenge=challenge)
                    visited.update(path)
                    self.assertLess(path.index("independent_baseline"), path.index("independent_verify"))
                    self.assertLess(path.index("independent_verify"), path.index("reviewer"))
                    self.assertEqual("test_design" in path, level != "low")
                    self.assertEqual("chief_plan" in path, level == "high")
                    self.assertEqual("chief_accept" in path, level == "high")
                    self.assertEqual("challenge_review" in path, challenge)
                    for observation_phase in ("verify", "independent_baseline", "independent_verify", "ci", "postmerge"):
                        self.assertEqual(verification_transition(observation_phase, True),
                                         next_phase(observation_phase, level=level, challenge=challenge))
        self.assertEqual(visited, {"architect", "test_design", "chief_plan", "developer", "verify",
                                   "tester", "independent_baseline", "independent_verify", "reviewer",
                                   "challenge_review", "architect_accept", "chief_accept", "publish",
                                   "ci", "merge", "postmerge"})

    def test_risk_review_return_cannot_skip_effect_or_evidence_gates(self):
        for stage in ("test_design", "chief_plan"):
            for target in ("publish", "ci", "merge", "postmerge", "done", "tester", "", False):
                with self.subTest(stage=stage, target=target), self.assertRaises(CoreError):
                    next_phase(stage, level="medium", return_phase=target)
        self.assertEqual(next_phase("test_design", level="medium", return_phase="verify"), "verify")
        self.assertEqual(next_phase("test_design", level="high", return_phase="verify"), "chief_plan")
        self.assertEqual(next_phase("chief_plan", return_phase="verify"), "verify")
        for challenge in (None, "false", 0, 1):
            with self.subTest(challenge=challenge), self.assertRaises(CoreError):
                next_phase("reviewer", challenge=challenge)

    def test_failed_counterfactual_cannot_advance_to_candidate_verification(self):
        self.assertEqual(verification_transition("independent_baseline", False), "tester")
        for value in (None, 0, 1, "false"):
            with self.subTest(value=value), self.assertRaises(CoreError):
                verification_transition("independent_baseline", value)

    def test_attempt_identity_and_retry_evidence_are_conservative(self):
        self.assertEqual(next_attempt(1, [{"attempt": 3}]), 4)
        for invalid in (True, False, 0, -1):
            with self.assertRaises(CoreError): next_attempt(invalid)
        self.assertEqual(retry_preconditions(baseline=True, regressions=True, negative_control=False), "BLOCKED_POLICY")
        self.assertEqual(retry_preconditions(baseline=True, regressions=False, negative_control=True), "FAILED_VERIFICATION")

    def test_upgrade_suspension_requires_unchanged_held_attempt_and_exact_goal(self):
        state = {"paused": True, "active": "A", "active_goal": "G", "goals": {"G": {"status": "active", "hash": "g"}},
                 "tasks": {"A": {"phase": "await_human", "base": "a", "head": "a", "goal_id": "G", "goal_hash": "g"}}}
        with self.assertRaises(CoreError): upgrade_boundary(state)
        self.assertEqual(upgrade_boundary(state, suspend=True)["suspend"], "A")
        for key, value in (("head", "changed"), ("pending", {"id": 1}), ("pr", 1), ("checkpoint_head", "a"), ("goal_hash", "other")):
            previous = state["tasks"]["A"].get(key)
            state["tasks"]["A"][key] = value
            with self.subTest(key=key), self.assertRaises(CoreError): upgrade_boundary(state, suspend=True)
            state["tasks"]["A"][key] = previous


class TypedAcceptanceConformance(unittest.TestCase):
    def criteria(self):
        kinds = ["behavior", "compatibility", "documentation", "ci", "delivery"]
        rows = [{"id": "AC-" + str(i), "text": kind} for i, kind in enumerate(kinds)]
        return acceptance_contract(rows, [{"criterion_id": row["id"], "kind": kind,
            "paths": ["docs/contracts.md"] if kind == "documentation" else [],
            "targets": ["candidate", "integration"] if kind == "ci" else []} for row, kind in zip(rows, kinds)])

    def test_product_tests_cannot_prove_future_delivery(self):
        criteria = self.criteria()
        self.assertEqual(len(test_criteria(criteria)), 2)
        before = evaluate_obligations(criteria, {"AC-0": True, "AC-1": True, "AC-2": True}, stage="candidate")
        self.assertTrue(before["passed"])
        self.assertFalse(before["complete"])
        self.assertEqual([r["status"] for r in before["rows"]][-2:], ["deferred", "deferred"])
        self.assertFalse(evaluate_obligations(criteria, {"AC-0": True}, stage="postmerge")["passed"])
        self.assertTrue(evaluate_obligations(criteria, {r["id"]: True for r in criteria}, stage="postmerge")["complete"])

    def test_future_role_claim_must_be_deferred_and_legacy_text_is_not_downgraded(self):
        delivery = self.criteria()[-1]
        self.assertFalse(evidence_status_valid(delivery, {"status": "covered", "evidence": "will merge"}))
        self.assertTrue(evidence_status_valid(delivery, {"status": "deferred", "evidence": "controller after merge"}))
        self.assertEqual(acceptance_contract([{"id": "A", "text": "PR is merged"}])[0]["kind"], "behavior")

    def test_invalid_kind_missing_identity_and_non_document_paths_are_rejected(self):
        criteria = [{"id": "A", "text": "Document the behavior"}]
        for kind, paths in (("unknown", []), ("documentation", []), ("documentation", ["../a.md"]),
                            ("documentation", ["src/api.py"]), ("documentation", ["docs/*.md"])):
            with self.subTest(kind=kind, paths=paths), self.assertRaises(CoreError):
                acceptance_contract(criteria, [{"criterion_id": "A", "kind": kind, "paths": paths, "targets": []}])
