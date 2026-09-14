from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from reference_runtime import conformance
from reference_runtime.base import BaseEngine
from reference_runtime.contracts import (
    digest_paths,
    load_json,
    matches_any,
    path_matches,
    safe_relative_path,
    validate_goal,
    validate_policy,
)
from reference_runtime.events import EventLog
from reference_runtime.executor import ExecutionResult, LocalFixtureExecutor
from reference_runtime.schema_validation import validate_json_file

ROOT = Path(__file__).resolve().parents[1]


class MatcherTests(unittest.TestCase):
    def test_double_star_matches_zero_or_more_segments(self):
        self.assertTrue(path_matches("src/security/guard.py", "src/**/security/**"))
        self.assertTrue(path_matches("src/reference_app/security/guard.py", "src/**/security/**"))
        self.assertFalse(path_matches("src/reference_app/security_helpers.py", "src/**/security/**"))

    def test_repository_paths_reject_traversal_absolute_and_noncanonical(self):
        self.assertEqual(safe_relative_path("src/reference_app/service.py"), "src/reference_app/service.py")
        for value in (
            "../authority.md",
            "src/../.agent-control/architecture.md",
            "/tmp/outside.py",
            "src//service.py",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_relative_path(value)

    def test_authority_snapshot_uses_same_matcher_and_is_nonempty(self):
        product = ROOT / "examples" / "minimal-product"
        policy = load_json(ROOT / "config" / "reference-policy.json")
        snapshot = digest_paths(product, policy["authority_paths"])
        self.assertGreaterEqual(len(snapshot["files"]), 8)
        self.assertIn(".agent-control/quality-gates.json", snapshot["files"])
        self.assertIn("ci/run_tests.py", snapshot["files"])
        self.assertIn(".github/workflows/ci.yml", snapshot["files"])


class PolicyAndReviewTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_json(ROOT / "config" / "reference-policy.json")

    def test_contract_documents_validate(self):
        validate_goal(load_json(ROOT / "examples" / "goal.example.json"))
        validate_policy(self.policy)
        validate_json_file(ROOT / "examples" / "goal.example.json", ROOT / "schemas" / "goal.schema.json")
        validate_json_file(ROOT / "config" / "reference-policy.json", ROOT / "schemas" / "policy.schema.json")

    def test_critical_and_medium_risk_are_reachable(self):
        engine = BaseEngine.__new__(BaseEngine)
        engine.policy = self.policy
        high, high_matches = engine.candidate_risk(["src/security/guard.py"])
        medium, medium_matches = engine.candidate_risk(["src/contract/schema.py"])
        low, _ = engine.candidate_risk(["src/reference_app/service.py"])
        self.assertEqual((high, medium, low), ("high", "medium", "low"))
        self.assertTrue(high_matches)
        self.assertTrue(medium_matches)

    def test_baseline_identity_loss_blocks_computed_review(self):
        engine = BaseEngine.__new__(BaseEngine)
        engine.policy = self.policy
        engine.authority = {"forbidden": {"enforced": []}}
        selected = load_json(ROOT / "examples" / "minimal-product" / ".agent-control" / "roadmap.json")["items"][0]
        baseline = {"test_identities": ["a.A.test_one", "a.A.test_two", "a.A.test_three"]}
        candidate = {
            "test_identities": ["fake.F.test_true"],
            "passed": True,
            "tested_sha": "a" * 40,
            "tests": 1,
        }
        snapshot = {"digest": "x", "files": {"a": "b"}}
        review = engine.compute_review(
            selected=selected,
            changed_paths=["src/reference_app/service.py"],
            policy_decisions=[{"accepted": True}],
            authority_before=snapshot,
            authority_after=snapshot,
            protected_before=snapshot,
            protected_after=snapshot,
            baseline=baseline,
            candidate_tests=candidate,
            candidate_sha="a" * 40,
        )
        self.assertEqual(review["verdict"], "block")
        kinds = {finding["kind"] for finding in review["blocking_findings"]}
        self.assertIn("missing-baseline-tests", kinds)
        self.assertIn("missing-acceptance-tests", kinds)
        self.assertFalse(review["checks"]["minimum_candidate_tests_met"])

    def test_developer_scope_does_not_include_tests(self):
        self.assertFalse(matches_any("tests/test_service.py", self.policy["developer_allowed_paths"]))
        self.assertTrue(matches_any("tests/test_acceptance_greet.py", self.policy["tester_allowed_paths"]))
        self.assertFalse(matches_any("tests/test_service.py", self.policy["tester_allowed_paths"]))


class _NoJUnitExecutor:
    def run(self, argv: list[str], cwd: Path) -> ExecutionResult:
        return ExecutionResult(
            argv=argv,
            returncode=2,
            stdout="",
            stderr="runner failed before writing junit",
            timed_out=False,
            duration_ms=1,
        )


class ExecutorAndEvidenceTests(unittest.TestCase):
    def test_local_executor_has_timeout_but_is_not_security_sandbox(self):
        result = LocalFixtureExecutor(1).run(
            ["python3", "-S", "-c", "import time; time.sleep(2)"],
            ROOT,
        )
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, 124)
        self.assertFalse(result.security_sandbox)

    def test_run_tests_does_not_reuse_stale_junit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            junit = root / "build" / "test-results" / "reference" / "TEST-reference.xml"
            junit.parent.mkdir(parents=True)
            junit.write_text(
                '<?xml version="1.0"?><testsuite tests="99" failures="0" errors="0" skipped="0">'
                '<testcase classname="stale" name="stale"/></testsuite>'
            )
            evidence = root / "evidence"
            evidence.mkdir()

            engine = BaseEngine.__new__(BaseEngine)
            engine.workspace = root
            engine.evidence = evidence
            engine.policy = {"minimum_candidate_tests": 5}
            engine.executor = _NoJUnitExecutor()
            engine.git = lambda *args, **kwargs: "a" * 40

            result = engine.run_tests("candidate")
            self.assertFalse(result["passed"])
            self.assertEqual(result["tests"], 0)
            self.assertEqual(result["test_identities"], [])
            self.assertFalse(junit.exists())

    def test_event_chain_detects_unrehashed_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            log = EventLog(path)
            log.append("one", {"x": 1})
            log.append("two", {"x": 2})
            path.write_text(path.read_text().replace('"x": 2', '"x": 99'))
            with self.assertRaises(ValueError):
                EventLog.verify(path)

    def test_event_chain_is_not_an_authenticity_signature(self):
        from reference_runtime.contracts import sha256_json

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            log = EventLog(path)
            log.append("one", {"x": 1})
            log.append("two", {"x": 2})
            events = [json.loads(line) for line in path.read_text().splitlines()]
            events[1]["payload"]["x"] = 99
            tip = "0" * 64
            for index, event in enumerate(events, 1):
                base = {
                    "seq": index,
                    "type": event["type"],
                    "payload": event["payload"],
                    "previous_hash": tip,
                }
                event.update(base)
                event["hash"] = sha256_json(base)
                tip = event["hash"]
            path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n")
            self.assertEqual(EventLog.verify(path)[1], tip)


class ConformanceHarnessTests(unittest.TestCase):
    def test_harness_records_failure_and_continues(self):
        original_names = conformance.scenario_names
        original_load = conformance.load_scenario
        original_run = conformance.run_request
        try:
            conformance.scenario_names = lambda root: ["a", "b"]
            conformance.load_scenario = lambda root, name: {
                "name": name,
                "expected_status": "COMPLETED",
                "fault_injection": None,
                "developer_fixture": "correct",
                "tester_fixture": "acceptance",
                "goal_overrides": {},
            }
            calls = {"count": 0}

            def fail(*args, **kwargs):
                calls["count"] += 1
                raise RuntimeError(f"boom-{calls['count']}")

            conformance.run_request = fail
            with tempfile.TemporaryDirectory() as directory:
                result = conformance.run_matrix(ROOT, Path(directory))
                self.assertFalse(result["passed"])
                self.assertEqual(len(result["scenarios"]), 2)
                self.assertTrue(all(not row["passed"] for row in result["scenarios"]))
                self.assertTrue((Path(directory) / "conformance-report.json").is_file())
        finally:
            conformance.scenario_names = original_names
            conformance.load_scenario = original_load
            conformance.run_request = original_run


if __name__ == "__main__":
    unittest.main()
