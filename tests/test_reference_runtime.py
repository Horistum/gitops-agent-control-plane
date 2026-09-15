from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from reference_runtime import conformance
from reference_runtime.base import BaseEngine, PolicyConfigurationError
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
from reference_runtime.probe_dsl import (
    ProbeContractError,
    evaluate_expression,
    materialize_cases,
    validate_probe,
)
from reference_runtime.schema_validation import (
    ARTIFACT_SCHEMAS,
    ARTIFACT_SCHEMA_PATTERNS,
    SchemaValidationError,
    load_schema,
    validate_json_file,
)
from reference_runtime.scenarios import build_request

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "examples" / "minimal-product"


class MatcherTests(unittest.TestCase):
    def test_double_star_matches_zero_or_more_segments(self):
        self.assertTrue(path_matches("src/security/guard.py", "src/**/security/**"))
        self.assertTrue(path_matches("src/reference_app/security/guard.py", "src/**/security/**"))
        self.assertFalse(path_matches("src/reference_app/security_helpers.py", "src/**/security/**"))

    def test_pathological_double_star_pattern_is_memoized(self):
        pattern = "/".join(["**"] * 14 + ["target.py"])
        path = "/".join([f"segment{i}" for i in range(20)] + ["target.py"])
        started = time.monotonic()
        self.assertTrue(path_matches(path, pattern))
        self.assertLess(time.monotonic() - started, 1.0)

    def test_repository_paths_reject_traversal_absolute_and_noncanonical(self):
        self.assertEqual(safe_relative_path("src/reference_app/service.py"), "src/reference_app/service.py")
        for value in ("../authority.md", "src/../.agent-control/architecture.md", "/tmp/outside.py", "src//service.py"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_relative_path(value)

    def test_authority_source_is_nonempty_and_owns_probe_definition(self):
        policy = load_json(ROOT / "config" / "reference-policy.json")
        snapshot = digest_paths(PRODUCT, policy["authority_paths"])
        self.assertGreaterEqual(len(snapshot["files"]), 9)
        self.assertIn(".agent-control/quality-gates.json", snapshot["files"])
        self.assertIn(".agent-control/verification-probes.json", snapshot["files"])
        self.assertIn("ci/run_tests.py", snapshot["files"])
        self.assertIn(".github/workflows/ci.yml", snapshot["files"])


class ProbeDslTests(unittest.TestCase):
    def test_dsl_supports_multiple_args_and_kwargs(self):
        probe = {
            "id": "multi",
            "target": "src/example.py",
            "callable": "combine",
            "cases": {
                "count": 2,
                "args": [
                    {"kind": "integer", "min": 1, "max": 3},
                    {"kind": "constant", "value": "x"},
                ],
                "kwargs": [
                    {"name": "flag", "generator": {"kind": "boolean"}},
                ],
            },
            "oracle": {
                "kind": "return-equals",
                "expected": {
                    "op": "concat",
                    "parts": [
                        {"op": "literal", "value": "prefix:"},
                        {"op": "arg", "index": 1},
                    ],
                },
            },
        }
        validate_probe(probe)
        cases = materialize_cases(probe)
        self.assertEqual(len(cases), 2)
        self.assertEqual(len(cases[0]["args"]), 2)
        self.assertIn("flag", cases[0]["kwargs"])
        self.assertEqual(
            evaluate_expression(probe["oracle"]["expected"], cases[0]["args"], cases[0]["kwargs"]),
            "prefix:x",
        )

    def test_dsl_rejects_unknown_exception_generator_and_expression(self):
        base = {
            "id": "x",
            "target": "src/x.py",
            "callable": "x",
            "cases": {"count": 1, "args": [{"kind": "null"}], "kwargs": []},
            "oracle": {"kind": "raises", "exception": "RuntimeError"},
        }
        with self.assertRaisesRegex(ProbeContractError, "unsupported exception"):
            validate_probe(base)
        bad_generator = json.loads(json.dumps(base))
        bad_generator["oracle"] = {"kind": "raises", "exception": "ValueError"}
        bad_generator["cases"]["args"] = [{"kind": "product-special"}]
        with self.assertRaisesRegex(ProbeContractError, "unsupported generator"):
            validate_probe(bad_generator)
        bad_expression = json.loads(json.dumps(base))
        bad_expression["oracle"] = {"kind": "return-equals", "expected": {"op": "product-special"}}
        with self.assertRaisesRegex(ProbeContractError, "unsupported expression"):
            validate_probe(bad_expression)


class PolicyAndReviewTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_json(ROOT / "config" / "reference-policy.json")

    def test_contract_documents_validate(self):
        validate_goal(load_json(ROOT / "examples" / "goal.example.json"))
        validate_policy(self.policy)
        validate_json_file(ROOT / "examples" / "goal.example.json", ROOT / "schemas" / "goal.schema.json")
        validate_json_file(ROOT / "config" / "reference-policy.json", ROOT / "schemas" / "policy.schema.json")
        validate_json_file(PRODUCT / ".agent-control" / "verification-probes.json", ROOT / "schemas" / "verification-probes.schema.json")

    def test_critical_and_medium_risk_are_reachable(self):
        engine = BaseEngine.__new__(BaseEngine)
        engine.policy = self.policy
        high, high_matches = engine.candidate_risk(["src/security/guard.py"])
        medium, medium_matches = engine.candidate_risk(["src/contract/schema.py"])
        low, _ = engine.candidate_risk(["src/reference_app/service.py"])
        self.assertEqual((high, medium, low), ("high", "medium", "low"))
        self.assertTrue(high_matches)
        self.assertTrue(medium_matches)

    def test_developer_scope_does_not_include_tests(self):
        self.assertFalse(matches_any("tests/test_service.py", self.policy["developer_allowed_paths"]))
        self.assertTrue(matches_any("tests/test_acceptance_greet.py", self.policy["tester_allowed_paths"]))
        self.assertFalse(matches_any("tests/test_service.py", self.policy["tester_allowed_paths"]))

    def test_quality_gate_flags_are_active_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            controller_product = Path(directory) / "controller-product"
            workspace = Path(directory) / "workspace"
            shutil.copytree(PRODUCT, controller_product)
            shutil.copytree(PRODUCT, workspace)
            (workspace / ".agent-control" / "verification-probes.json").unlink()
            gates_path = workspace / ".agent-control" / "quality-gates.json"
            gates = json.loads(gates_path.read_text())
            gates["require_controller_probes"] = False
            gates_path.write_text(json.dumps(gates))
            engine = BaseEngine.__new__(BaseEngine)
            engine.workspace = workspace
            engine.controller_authority_dir = controller_product / ".agent-control"
            with self.assertRaisesRegex(PolicyConfigurationError, "require_controller_probes"):
                engine.load_authority()

    def test_probe_contract_rejects_old_fixed_tuple_format(self):
        fixed_example = {
            "id": "x", "target": "src/x.py", "callable": "x",
            "args": ["public"], "kwargs": {}, "expect": {"return": "public"},
        }
        with self.assertRaisesRegex(PolicyConfigurationError, "fields invalid"):
            BaseEngine._validate_probe(fixed_example)

    def test_proposal_source_guard_is_rechecked_on_resume_path(self):
        engine = BaseEngine.__new__(BaseEngine)
        engine.request = {"proposal_source": "external-model"}
        engine.policy = {"executor_mode": "trusted-fixture-local"}
        with self.assertRaises(ValueError):
            engine._validate_proposal_source()

    def test_review_uses_controller_probe_result_not_junit_names(self):
        engine = BaseEngine.__new__(BaseEngine)
        engine.authority = {"quality_gates": {
            "protect_baseline_test_files": True,
            "require_controller_probes": True,
            "require_negative_control": True,
            "bind_probes_to_exact_git_sha": True,
            "require_diagnostic_junit_green": True,
        }}
        snapshot = {"digest": "same", "files": {"authority": "digest"}}
        review = engine.compute_review(
            changed_paths=["src/reference_app/service.py"],
            policy_decisions=[{"accepted": True}],
            authority_before=snapshot,
            authority_after=snapshot,
            protected_before=snapshot,
            protected_after=snapshot,
            diagnostic_tests={"passed": True},
            candidate_probes={"all_passed": False, "tested_sha": "a" * 40},
            negative_control={"negative_control_passed": True},
            candidate_sha="a" * 40,
        )
        self.assertEqual(review["verdict"], "block")
        self.assertFalse(review["checks"]["controller_probes_green"])

    def test_candidate_workspace_does_not_contain_probe_definition(self):
        goal = load_json(ROOT / "examples" / "goal.example.json")
        request = build_request(ROOT, "happy-path", goal)
        with tempfile.TemporaryDirectory() as directory:
            engine = BaseEngine(ROOT, request, Path(directory))
            self.assertFalse((engine.workspace / ".agent-control" / "verification-probes.json").exists())
            self.assertTrue(engine.verification_definition_path().is_file())
            self.assertEqual(engine.authority["verification_probes"]["schema"], 3)

    def test_negative_control_requires_every_case_to_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = BaseEngine.__new__(BaseEngine)
            engine.evidence = Path(directory)
            engine.acceptance_probe_ids = lambda selected: {"acceptance"}
            cases = [
                {"completed": True, "passed": i < 9}
                for i in range(10)
            ]
            engine.run_probes = lambda *args, **kwargs: {
                "schema": 3,
                "label": "negative-control",
                "tested_sha": "a" * 40,
                "verification_definition_sha256": "b" * 64,
                "probe_ids": ["acceptance"],
                "probes": [{
                    "probe_id": "acceptance",
                    "receipt_valid": True,
                    "completed": True,
                    "passed": False,
                    "receipt": {"cases": cases},
                }],
                "all_completed": True,
                "all_passed": False,
                "authoritative_within_trusted_fixture_scope": True,
            }
            result = engine.run_negative_control({"acceptance": [{"id": "AC-1", "probe_ids": ["acceptance"]}]})
            self.assertFalse(result["negative_control_passed"])
            self.assertFalse(result["negative_control_all_cases_rejected"])
            self.assertEqual(result["negative_control_case_count"], 10)


class _NoJUnitExecutor:
    def run(self, argv: list[str], cwd: Path, **kwargs) -> ExecutionResult:
        return ExecutionResult(argv=argv, returncode=2, stdout="", stderr="runner failed before writing junit", timed_out=False, duration_ms=1)


class _CaptureExecutor:
    def __init__(self):
        self.argv: list[str] | None = None
        self.control_payload: bytes | None = None

    def run(self, argv: list[str], cwd: Path, **kwargs) -> ExecutionResult:
        self.argv = list(argv)
        self.control_payload = kwargs.get("control_payload")
        return ExecutionResult(argv=argv, returncode=2, stdout="", stderr="captured", timed_out=False, duration_ms=1)


class ExecutorAndEvidenceTests(unittest.TestCase):
    def test_local_executor_has_timeout_but_is_not_security_sandbox(self):
        result = LocalFixtureExecutor(1).run([sys.executable, "-S", "-c", "import time; time.sleep(2)"], ROOT)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, 124)
        self.assertFalse(result.security_sandbox)
        self.assertEqual(result.cpu_limit_seconds, 2)

    def test_timeout_kills_descendant_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "grandchild-survived"
            child_code = f"import time; time.sleep(2); open({str(marker)!r}, 'w').write('survived')"
            parent_code = "import subprocess,sys,time; " + f"subprocess.Popen([sys.executable,'-c',{child_code!r}]); " + "time.sleep(30)"
            result = LocalFixtureExecutor(1).run([sys.executable, "-S", "-c", parent_code], ROOT)
            self.assertTrue(result.timed_out)
            time.sleep(2.2)
            self.assertFalse(marker.exists())

    def test_large_control_payload_has_live_reader_and_does_not_deadlock(self):
        code = (
            "import argparse,os; p=argparse.ArgumentParser(); p.add_argument('--control-fd',type=int,required=True); "
            "a=p.parse_args(); data=b''; "
            "exec(\"while True:\\n c=os.read(a.control_fd,65536)\\n if not c: break\\n data+=c\"); "
            "os.close(a.control_fd); print(len(data))"
        )
        payload = b"x" * (128 * 1024)
        result = LocalFixtureExecutor(3).run([sys.executable, "-S", "-c", code], ROOT, control_payload=payload)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.returncode, 0)
        self.assertIn(str(len(payload)), result.stdout)

    def test_run_tests_does_not_reuse_stale_junit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            junit = root / "build" / "test-results" / "reference" / "TEST-reference.xml"
            junit.parent.mkdir(parents=True)
            junit.write_text('<?xml version="1.0"?><testsuite tests="99" failures="0" errors="0" skipped="0"><testcase classname="stale" name="stale"/></testsuite>')
            evidence = root / "evidence"
            evidence.mkdir()
            engine = BaseEngine.__new__(BaseEngine)
            engine.workspace = root
            engine.evidence = evidence
            engine.executor = _NoJUnitExecutor()
            engine.git = lambda *args, **kwargs: "a" * 40
            result = engine.run_tests("candidate")
            self.assertFalse(result["passed"])
            self.assertEqual(result["tests"], 0)
            self.assertEqual(result["test_identities"], [])
            self.assertFalse(junit.exists())
            self.assertFalse(result["authoritative"])

    def test_probe_secret_and_definition_are_not_in_controller_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            evidence.mkdir()
            capture = _CaptureExecutor()
            engine = BaseEngine.__new__(BaseEngine)
            engine.repo = ROOT
            engine.workspace = root
            engine.evidence = evidence
            engine.executor = capture
            engine.controller_authority_dir = PRODUCT / ".agent-control"
            probe = load_json(PRODUCT / ".agent-control" / "verification-probes.json")["acceptance"][0]
            engine.authority = {"verification_probes": {"baseline": [], "acceptance": [probe]}}
            engine.git = lambda *args, **kwargs: "a" * 40
            result = engine.run_probes("candidate", {probe["id"]})
            joined = " ".join(capture.argv or [])
            self.assertNotIn("--nonce", joined)
            self.assertNotIn("--probe-json", joined)
            self.assertNotIn("receipt_key", joined)
            self.assertNotIn("--control-fd", joined)
            self.assertIsNotNone(capture.control_payload)
            self.assertFalse(result["all_completed"])

    def test_probe_requires_parent_signed_completion_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "service.py").write_text("import os\nos._exit(0)\n")
            evidence = root / "evidence"
            evidence.mkdir()
            controller = Path(directory) / "controller"
            controller.mkdir()
            probe = {
                "id": "exit-zero",
                "target": "src/service.py",
                "callable": "value",
                "cases": {"count": 1, "args": [{"kind": "constant", "value": "x"}], "kwargs": []},
                "oracle": {"kind": "return-equals", "expected": {"op": "literal", "value": "x"}},
            }
            (controller / "verification-probes.json").write_text(json.dumps({"schema": 3, "baseline": [probe], "acceptance": [probe]}))
            engine = BaseEngine.__new__(BaseEngine)
            engine.repo = ROOT
            engine.workspace = root
            engine.evidence = evidence
            engine.executor = LocalFixtureExecutor(2)
            engine.controller_authority_dir = controller
            engine.authority = {"verification_probes": {"baseline": [probe], "acceptance": [probe]}}
            engine.git = lambda *args, **kwargs: "a" * 40
            result = engine.run_probes("candidate", {"exit-zero"})
            self.assertFalse(result["all_completed"])
            self.assertFalse(result["all_passed"])
            row = result["probes"][0]
            self.assertEqual(row["receipt_count"], 1)
            self.assertTrue(row["receipt_valid"])
            self.assertFalse(row["receipt"]["completed"])

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
                base = {"seq": index, "type": event["type"], "payload": event["payload"], "previous_hash": tip}
                event.update(base)
                event["hash"] = sha256_json(base)
                tip = event["hash"]
            path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n")
            self.assertEqual(EventLog.verify(path)[1], tip)

    def test_effect_id_requires_final_git_trailer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            (root / "a").write_text("1")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "Subject", "-m", "Effect-Id: abc", "-m", "not-a-trailer"], cwd=root, check=True, capture_output=True)
            engine = BaseEngine.__new__(BaseEngine)
            engine.workspace = root
            self.assertEqual(engine.effect_merge_commits("abc"), [])
            (root / "a").write_text("2")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "Subject", "-m", "Effect-Id: abc"], cwd=root, check=True, capture_output=True)
            self.assertEqual(len(engine.effect_merge_commits("abc")), 1)


class SchemaTests(unittest.TestCase):
    def test_unknown_json_schema_keyword_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.json"
            path.write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "string", "oneOf": [{"const": "x"}]}))
            with self.assertRaisesRegex(SchemaValidationError, "unsupported JSON Schema keywords"):
                load_schema(path)

    def test_schema_valued_additional_properties_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.json"
            path.write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "minProperties": 1,
                "additionalProperties": {"type": "string", "pattern": "[0-9a-f]{64}"},
            }))
            schema = load_schema(path)
            from reference_runtime.schema_validation import validate_instance
            validate_instance({"a": "f" * 64}, schema)
            with self.assertRaises(SchemaValidationError):
                validate_instance({"a": "not-a-digest"}, schema)

    def test_critical_safety_artifacts_have_schema_mapping(self):
        for name in ("merge-intent.json", "human-decision.json", "proposal.json", "request.json"):
            self.assertIn(name, ARTIFACT_SCHEMAS)
        sample_names = ("authority-snapshot-baseline.json", "protected-tests-candidate.json", "role-reviewer.json")
        for name in sample_names:
            self.assertTrue(any(pattern.fullmatch(name) for pattern, _ in ARTIFACT_SCHEMA_PATTERNS), name)


class ConformanceHarnessTests(unittest.TestCase):
    def test_harness_records_failure_and_continues(self):
        original_names = conformance.scenario_names
        original_load = conformance.load_scenario
        original_run = conformance.run_request
        try:
            conformance.scenario_names = lambda root: ["a", "b"]
            conformance.load_scenario = lambda root, name: {
                "schema": 2,
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
