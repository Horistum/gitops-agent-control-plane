from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_runtime.actions import action
from agent_runtime.controller import Controller
from agent_runtime.decisions import decision_document
from agent_runtime.io import Closed
from agent_runtime.observations import status_document
from agent_runtime.recovery import task_recovery
from reference_runtime import _schema_validation_impl as validation_impl
from reference_runtime import schema_validation as validation
from reference_runtime._conformance_impl import _request_from_spec
from reference_runtime.attempts import CandidateAttemptMixin
from reference_runtime.base import BaseEngine
from reference_runtime.contracts import load_json
from reference_runtime.scenarios import build_request, build_request_from_spec, load_scenario, scenario_names
from runtime_support import ROOT, InProcessProvider, build_product, goal, policy


class ScenarioBuilderTests(unittest.TestCase):
    def test_all_scenarios_use_identical_requests_and_preserve_input_prose(self):
        base = load_json(ROOT / "examples/goal.example.json")
        base["success_condition"] = "Preserve the owner's original product objective."
        names = scenario_names(ROOT)
        self.assertTrue(names)
        for name in names:
            with self.subTest(name=name):
                spec = load_scenario(ROOT, name)
                original = deepcopy((spec, base))
                public = build_request(ROOT, name, base)
                self.assertEqual(public, _request_from_spec(ROOT, spec, base))
                self.assertEqual(public, build_request_from_spec(spec, base))
                self.assertEqual(public["goal"]["success_condition"], base["success_condition"])
                public["goal"]["autonomy"]["max_cycles"] = 999
                public["goal"]["items"].append("LOCAL-ONLY")
                self.assertEqual((spec, base), original)

    def test_goal_items_are_explicit_and_never_inferred_from_scenario_name(self):
        base = load_json(ROOT / "examples/goal.example.json")
        spec = load_scenario(ROOT, "autonomous-two-item")
        self.assertEqual(build_request_from_spec(spec, base)["goal"]["items"], spec["goal_items"])
        spec.pop("goal_items")
        for name in ("autonomous-two-item", "new-scenario"):
            spec["name"] = name
            self.assertEqual(build_request_from_spec(spec, base)["goal"]["items"], ["EXAMPLE-001"])
        for invalid in ([], None, "EXAMPLE-001"):
            spec["goal_items"] = invalid
            with self.assertRaises(ValueError):
                build_request_from_spec(spec, base)
        spec.pop("goal_items")
        spec["goal_overrides"] = {"success_condition": "silently replace prose"}
        with self.assertRaises(ValueError):
            build_request_from_spec(spec, base)


class SharedValidationTests(unittest.TestCase):
    def test_exact_name_pattern_order_and_events_remain_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            schemas = root / "schemas"
            evidence.mkdir(); schemas.mkdir()
            for kind in ("exact", "pattern", "unused", "event"):
                (schemas / f"{kind}.schema.json").write_text(json.dumps({
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object", "properties": {"kind": {"const": kind}},
                    "required": ["kind"], "additionalProperties": False,
                }))
            for name, kind in (("exact.json", "exact"), ("z.json", "pattern"), ("a.json", "pattern")):
                (evidence / name).write_text(json.dumps({"kind": kind}))
            (evidence / "events.jsonl").write_text('{"kind":"event"}\n')
            exact = {"exact.json": "exact.schema.json"}
            patterns = ((re.compile(r".*\.json"), "pattern.schema.json"),
                        (re.compile(r".*\.json"), "unused.schema.json"))
            with patch.object(validation, "ARTIFACT_SCHEMAS", exact), \
                 patch.object(validation, "ARTIFACT_SCHEMA_PATTERNS", patterns):
                self.assertEqual(validation.validate_evidence_directory(root, evidence),
                                 ["exact.json", "a.json", "z.json", "events.jsonl"])
            self.assertEqual(validation_impl.validate_evidence_directory(
                root, evidence, artifact_schemas={}, artifact_schema_patterns=()), ["events.jsonl"])

    def test_public_extensions_are_forwarded_and_invalid_recovery_artifacts_fail(self):
        names = {"control-state-intent.json", "control-state-recovery.json", "phase-recovery.json",
                 "control-state-intent-example-001.json", "retry-preconditions-example-001-attempt-01.json"}
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            for name in names:
                (evidence / name).write_text("{}")
            with patch.object(validation_impl, "validate_evidence_directory", wraps=validation_impl.validate_evidence_directory) as shared, \
                 patch.object(validation_impl, "validate_json_file") as validate_file:
                self.assertEqual(set(validation.validate_evidence_directory(ROOT, evidence)), names)
                shared.assert_called_once_with(ROOT, evidence, artifact_schemas=validation.ARTIFACT_SCHEMAS,
                                               artifact_schema_patterns=validation.ARTIFACT_SCHEMA_PATTERNS)
                self.assertEqual(validate_file.call_count, len(names))
            with self.assertRaises(validation.SchemaValidationError):
                validation.validate_evidence_directory(ROOT, evidence)


class RuntimeConsolidationTests(unittest.TestCase):
    def test_shadow_base_lifecycle_is_not_available(self):
        for name in ("select_authorized_item", "rollback_uncommitted_candidate", "prepare_merge_effect",
                     "effect_merge_commits", "perform_merge_effect", "consume_merge_effect"):
            self.assertFalse(hasattr(BaseEngine, name), name)

    def test_outer_attempt_bounds_own_catalog_and_budget_exhaustion(self):
        cases = ((0, 3, "REPAIR_REQUESTED", 0, "catalog"),
                 (1, 3, "REPAIR_REQUESTED", 1, "catalog"),
                 (3, 1, "REPAIR_REQUESTED", 1, "budget"),
                 (1, 1, "COMPLETED", 1, None))
        for length, limit, outcome, expected_calls, reason in cases:
            with self.subTest(length=length, limit=limit, outcome=outcome), tempfile.TemporaryDirectory() as directory:
                calls, cycles = [], []
                def attempt(selected, number, prior):
                    self.assertLessEqual(number, length)
                    calls.append(number)
                    return outcome, {"feedback": "repair"}
                engine = SimpleNamespace(
                    request={"work_catalog": {"EXAMPLE-001": [{}] * length}},
                    goal={"autonomy": {"max_attempts_per_item": limit}},
                    policy={"max_attempts_per_item": limit}, state={}, evidence=Path(directory),
                    _attempt_work=attempt, _append_cycle=lambda *args: cycles.append(args),
                    finish=lambda status, **kwargs: {"status": status, **kwargs},
                )
                result = CandidateAttemptMixin._run_selected_item(engine, {"id": "EXAMPLE-001"})
                self.assertEqual(len(calls), expected_calls)
                self.assertEqual(len(cycles), 1)
                if reason is None:
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result["status"], "FAILED_VERIFICATION")
                    self.assertIn(reason, result["reason"])
                    self.assertEqual(engine.state["goal_status"], "BLOCKED")


class RecoveryProjectionTests(unittest.TestCase):
    def start(self, root, context_limit):
        product = root / "product"
        build_product(product)
        configuration = policy(product)
        configuration["limits"]["context_rounds"] = context_limit
        engine = Controller.start(root / "run", configuration, goal(), trusted_local=True)
        engine.reasoning = InProcessProvider()
        engine.tick()
        self.assertIsNotNone(engine.task)
        return engine

    def test_actual_policy_limit_is_shared_by_status_decision_and_retry_action(self):
        for limit, rounds, permitted in ((1, 0, True), (1, 1, False), (12, 8, True), (12, 12, False)):
            with self.subTest(limit=limit, rounds=rounds), tempfile.TemporaryDirectory() as directory:
                engine = self.start(Path(directory), limit)
                engine.task["context_rounds"] = rounds
                engine.hold("Fixture verification failure")
                engine.store.save()
                before = deepcopy(engine.state)
                self.assertIs(status_document(engine.state)["recovery"]["retry"], permitted)
                self.assertIs("retry" in decision_document(engine.state)["actions"], permitted)
                self.assertEqual(engine.state, before)
                if permitted:
                    result = action(engine.root, "retry")
                    self.assertEqual(result["status"], "RUNNING")
                else:
                    with self.assertRaisesRegex(Closed, "not retryable"):
                        action(engine.root, "retry")
                restored = Controller(engine.root)
                self.assertEqual(restored.state["model_calls"], before["model_calls"])
                self.assertEqual(restored.task["context_rounds"], rounds)

    def test_real_context_limit_hold_still_refuses_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.start(Path(directory), 1)
            engine.task.update(phase="architect", context_rounds=1)
            engine.store.save()
            before_calls = engine.state["model_calls"]
            result = engine.tick()
            self.assertEqual(result["status"], "BLOCKED_POLICY")
            self.assertEqual(result["diagnostic"]["code"], "CONTEXT_LIMIT")
            self.assertFalse(result["recovery"]["retry"])
            self.assertFalse(engine.task["retryable"])
            with self.assertRaisesRegex(Closed, "not retryable"):
                action(engine.root, "retry")
            self.assertEqual(Controller(engine.root).state["model_calls"], before_calls)

    def test_recovery_view_maps_failure_pending_replan_and_lifetime_budget_without_mutation(self):
        state = {"task": {"id": "TASK-1", "phase": "await_human", "hold_kind": "FAILED", "retryable": True},
                 "policy": {"limits": {"model_calls": 20, "context_rounds": 12}},
                 "model_calls": 1, "owner_replans": {"TASK-1": 2}}
        original = deepcopy(state)
        self.assertEqual(task_recovery(state), {"retry": True, "replan": False})
        self.assertEqual(state, original)
        for alteration in ({"diagnostic": {"code": "CONTEXT_LIMIT"}},
                           {"pending": {"kind": "model", "id": "pending"}}, {"model_calls": 20}):
            self.assertFalse(task_recovery({**state, **alteration})["retry"])


if __name__ == "__main__":
    unittest.main()
