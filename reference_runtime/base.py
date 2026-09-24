from __future__ import annotations

import difflib
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from .contracts import (
    canonical_json,
    digest_paths,
    load_json,
    matches_any,
    risk_rank,
    safe_relative_path,
    sha256_bytes,
    sha256_json,
    validate_goal,
    validate_policy,
)
from .events import EventLog
from .persistence import atomic_json
from .executor import LocalFixtureExecutor
from .probe_dsl import ProbeContractError, validate_probe


class InjectedCrash(RuntimeError):
    pass


class PolicyConfigurationError(RuntimeError):
    pass


class BaseEngine:
    def __init__(self, repository_root: Path, request: dict, output_root: Path, *, run_id: str | None = None):
        self.repo = repository_root.resolve()
        self.request = request
        self.label = request["label"]
        self.output_root = output_root.resolve()
        self.product_source = self.repo / "examples" / "minimal-product"
        self.controller_authority_dir = self.product_source / ".agent-control"
        self.goal = request["goal"]
        self.policy = load_json(self.repo / "config" / "reference-policy.json")
        validate_goal(self.goal)
        validate_policy(self.policy)
        self._validate_proposal_source()

        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_id = run_id or f"{stamp}-{self.label}-{sha256_json({'label': self.label, 'ns': time.time_ns()})[:8]}"
        self.run_dir = self.output_root / self.run_id
        self.workspace = self.run_dir / "workspace"
        self.evidence = self.run_dir / "evidence"
        self.evidence.mkdir(parents=True, exist_ok=False)

        verifier_source = (self.controller_authority_dir / "verification-probes.json").resolve()

        def ignore_controller_only(source: str, names: list[str]) -> set[str]:
            if Path(source).resolve() == verifier_source.parent and "verification-probes.json" in names:
                return {"verification-probes.json"}
            return set()

        shutil.copytree(self.product_source, self.workspace, ignore=ignore_controller_only)
        self.events = EventLog(self.evidence / "events.jsonl")
        self.executor = LocalFixtureExecutor(self.policy["test_timeout_seconds"])
        self.state = {
            "schema": 2,
            "run_id": self.run_id,
            "label": self.label,
            "status": "RUNNING",
            "phase": "INITIALIZING",
            "base_sha": None,
            "candidate_sha": None,
            "merge_sha": None,
            "risk": self.policy["default_risk"],
            "pending_effect": None,
            "event_tip": None,
        }
        self.write_json("request.json", request)
        self.write_json("goal.json", self.goal)
        self.write_json("policy.json", self.policy)
        self.save_state()
        self.authority_error: str | None = None
        try:
            self.authority = self.load_authority()
        except PolicyConfigurationError as exc:
            self.authority = {}
            self.authority_error = str(exc)

    @classmethod
    def resume_from(cls, repository_root: Path, run_dir: Path) -> "BaseEngine":
        obj = cls.__new__(cls)
        obj.repo = repository_root.resolve()
        obj.run_dir = run_dir.resolve()
        obj.output_root = obj.run_dir.parent
        obj.workspace = obj.run_dir / "workspace"
        obj.evidence = obj.run_dir / "evidence"
        obj.request = load_json(obj.evidence / "request.json")
        obj.label = obj.request["label"]
        obj.goal = load_json(obj.evidence / "goal.json")
        obj.policy = load_json(obj.evidence / "policy.json")
        validate_goal(obj.goal)
        validate_policy(obj.policy)
        obj._validate_proposal_source()
        obj.product_source = obj.repo / "examples" / "minimal-product"
        obj.controller_authority_dir = obj.product_source / ".agent-control"
        obj.events = EventLog(obj.evidence / "events.jsonl")
        obj.executor = LocalFixtureExecutor(obj.policy["test_timeout_seconds"])
        obj.state = load_json(obj.evidence / "state.json")
        obj.run_id = obj.state["run_id"]
        obj.authority_error = None
        try:
            obj.authority = obj.load_authority()
        except PolicyConfigurationError as exc:
            obj.authority = {}
            obj.authority_error = str(exc)
        return obj

    def _validate_proposal_source(self) -> None:
        if self.request.get("proposal_source") != "trusted-fixture" or self.policy["executor_mode"] != "trusted-fixture-local":
            raise ValueError("standalone runtime refuses non-fixture/untrusted proposal sources without a real sandbox")

    @staticmethod
    def _validate_probe(probe: dict) -> None:
        try:
            validate_probe(probe)
            safe_relative_path(probe["target"])
        except (ProbeContractError, TypeError, ValueError) as exc:
            raise PolicyConfigurationError(f"verification probe invalid: {exc}") from exc

    def verification_definition_path(self) -> Path:
        return self.controller_authority_dir / "verification-probes.json"

    def verification_definition_digest(self) -> str:
        return sha256_bytes(self.verification_definition_path().read_bytes())

    def load_authority(self) -> dict:
        authority_dir = self.workspace / ".agent-control"
        if (authority_dir / "verification-probes.json").exists():
            raise PolicyConfigurationError("controller-only verification probes leaked into candidate workspace")
        value = {
            "roadmap": load_json(authority_dir / "roadmap.json"),
            "quality_gates": load_json(authority_dir / "quality-gates.json"),
            "forbidden": load_json(authority_dir / "forbidden.json"),
            "release_state": load_json(authority_dir / "release-state.json"),
            "verification_probes": load_json(self.verification_definition_path()),
        }
        gates = value["quality_gates"]
        expected_flags = {
            "protect_baseline_test_files",
            "require_controller_probes",
            "require_negative_control",
            "bind_probes_to_exact_git_sha",
            "require_diagnostic_junit_green",
        }
        if gates.get("schema") != 3 or set(gates) != {"schema", *expected_flags}:
            raise PolicyConfigurationError("quality-gates.json fields invalid")
        for flag in expected_flags:
            if gates.get(flag) is not True:
                raise PolicyConfigurationError(f"required quality gate disabled: {flag}")

        probes = value["verification_probes"]
        if probes.get("schema") != 3 or not isinstance(probes.get("baseline"), list) or not isinstance(probes.get("acceptance"), list):
            raise PolicyConfigurationError("verification-probes.json shape invalid")
        all_probes = probes["baseline"] + probes["acceptance"]
        if not probes["baseline"] or not probes["acceptance"]:
            raise PolicyConfigurationError("baseline and acceptance probe sets must both be non-empty")
        for probe in all_probes:
            self._validate_probe(probe)
        ids = [probe["id"] for probe in all_probes]
        if len(ids) != len(set(ids)):
            raise PolicyConfigurationError("verification probe ids must be unique")
        return value

    def write_json(self, name: str, value: dict | list) -> Path:
        path = self.evidence / name
        atomic_json(path, value)
        return path

    def save_state(self) -> None:
        self.state["event_tip"] = self.events.tip
        self.write_json("state.json", self.state)

    def event(self, event_type: str, payload: dict) -> None:
        self.events.append(event_type, payload)
        self.save_state()

    def transition(self, phase: str, *, status: str = "RUNNING") -> None:
        self.state["phase"] = phase
        self.state["status"] = status
        self.event("state-transition", {"phase": phase, "status": status})

    def git(self, *args: str, capture: bool = True, check: bool = True) -> str:
        p = subprocess.run(["git", *args], cwd=self.workspace, text=True, capture_output=capture)
        if check and p.returncode:
            raise RuntimeError(f"git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()}")
        return p.stdout.strip() if capture else ""

    def init_git(self) -> str:
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Reference Runtime")
        self.git("config", "user.email", "reference-runtime@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", ".")
        self.git("commit", "-m", "Reference baseline")
        return self.git("rev-parse", "HEAD")

    def run_tests(self, label: str) -> dict:
        """Run the protected JUnit suite as diagnostic evidence, not as sole proof."""
        junit = self.workspace / "build" / "test-results" / "reference" / "TEST-reference.xml"
        if junit.exists():
            junit.unlink()
        tested_sha = self.git("rev-parse", "HEAD")
        result_exec = self.executor.run([sys.executable, "-S", "ci/run_tests.py"], self.workspace)
        tests = failures = errors = skipped = 0
        identities: list[str] = []
        parse_error = None
        if junit.is_file():
            try:
                suite = ET.parse(junit).getroot()
                tests = int(suite.attrib.get("tests", "0"))
                failures = int(suite.attrib.get("failures", "0"))
                errors = int(suite.attrib.get("errors", "0"))
                skipped = int(suite.attrib.get("skipped", "0"))
                identities = sorted(f"{case.attrib.get('classname')}.{case.attrib.get('name')}" for case in suite.iter("testcase"))
            except Exception as exc:
                parse_error = f"{type(exc).__name__}: {exc}"
        result = {
            "schema": 2,
            "label": label,
            "tested_sha": tested_sha,
            "exit_code": result_exec.returncode,
            "timed_out": result_exec.timed_out,
            "duration_ms": result_exec.duration_ms,
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "test_identities": identities,
            "junit_parse_error": parse_error,
            "stdout_sha256": sha256_bytes(result_exec.stdout.encode()),
            "stderr_sha256": sha256_bytes(result_exec.stderr.encode()),
            "executor": {
                "isolation": result_exec.isolation,
                "security_sandbox": result_exec.security_sandbox,
                "trusted_fixture_only": True,
                "process_group_terminated": result_exec.process_group_terminated,
                "cpu_limit_seconds": result_exec.cpu_limit_seconds,
            },
            "passed": result_exec.returncode == 0 and not result_exec.timed_out and parse_error is None and failures == 0 and errors == 0 and tests >= 1,
            "authoritative": False,
        }
        self.write_json(f"test-{label}.json", result)
        return result

    def _probe_index(self) -> dict[str, dict]:
        probes = self.authority["verification_probes"]
        return {probe["id"]: probe for probe in probes["baseline"] + probes["acceptance"]}

    def acceptance_probe_ids(self, selected: dict) -> set[str]:
        result: set[str] = set()
        for criterion in selected["acceptance"]:
            if criterion.get("kind", "behavior") not in {"behavior", "compatibility"}:
                continue
            ids = criterion.get("probe_ids")
            if not isinstance(ids, list) or not ids:
                raise PolicyConfigurationError(f"acceptance criterion {criterion.get('id')} has no probe_ids")
            result.update(ids)
        known = set(self._probe_index())
        missing = result - known
        if missing:
            raise PolicyConfigurationError(f"roadmap references unknown verification probes: {sorted(missing)}")
        return result

    @staticmethod
    def _receipt_mac(receipt: dict, key: bytes) -> str:
        return hmac.new(key, canonical_json(receipt).encode("utf-8"), hashlib.sha256).hexdigest()

    def run_probes(self, label: str, probe_ids: set[str], *, persist: bool = True) -> dict:
        tested_sha = self.git("rev-parse", "HEAD")
        index = self._probe_index()
        worker = self.repo / "reference_runtime" / "probe_worker.py"
        definition_digest = self.verification_definition_digest()
        rows: list[dict] = []
        for probe_id in sorted(probe_ids):
            probe = index[probe_id]
            receipt_key = secrets.token_bytes(32)
            challenge = secrets.token_hex(16)
            control = {
                "receipt_key": receipt_key.hex(),
                "challenge": challenge,
                "probe": probe,
            }
            control_payload = canonical_json(control).encode("utf-8")
            if len(control_payload) > 262144:
                raise PolicyConfigurationError("verification probe control payload exceeds 256 KiB")
            execution = self.executor.run(
                [sys.executable, "-S", str(worker), "--workspace", str(self.workspace)],
                self.workspace,
                control_payload=control_payload,
            )

            prefix = "REFERENCE_PROBE_RECEIPT="
            receipt_lines = [line for line in execution.stdout.splitlines() if line.startswith(prefix)]
            receipt = None
            receipt_valid = False
            if len(receipt_lines) == 1:
                try:
                    candidate_envelope = json.loads(receipt_lines[0][len(prefix):])
                    candidate_receipt = candidate_envelope.get("receipt") if isinstance(candidate_envelope, dict) else None
                    candidate_mac = candidate_envelope.get("hmac_sha256") if isinstance(candidate_envelope, dict) else None
                    if isinstance(candidate_receipt, dict) and isinstance(candidate_mac, str):
                        mac_ok = hmac.compare_digest(self._receipt_mac(candidate_receipt, receipt_key), candidate_mac)
                        identity_ok = (
                            candidate_receipt.get("protocol") == 3
                            and candidate_receipt.get("challenge") == challenge
                            and candidate_receipt.get("probe_id") == probe_id
                        )
                        if mac_ok and identity_ok:
                            receipt = candidate_receipt
                            receipt_valid = True
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

            completed = bool(receipt_valid and receipt and receipt.get("completed") is True)
            passed = bool(
                completed
                and receipt.get("passed") is True
                and execution.returncode == 0
                and not execution.timed_out
            )
            rows.append({
                "probe_id": probe_id,
                "definition_sha256": sha256_json(probe),
                "receipt_count": len(receipt_lines),
                "receipt_valid": receipt_valid,
                "completed": completed,
                "passed": passed,
                "receipt": receipt if receipt_valid else None,
                "worker_exit_code": execution.returncode,
                "timed_out": execution.timed_out,
                "duration_ms": execution.duration_ms,
                "stdout_sha256": sha256_bytes(execution.stdout.encode()),
                "stderr_sha256": sha256_bytes(execution.stderr.encode()),
            })
        result = {
            "schema": 3,
            "label": label,
            "tested_sha": tested_sha,
            "verification_definition_sha256": definition_digest,
            "probe_ids": sorted(probe_ids),
            "probes": rows,
            "all_completed": bool(rows) and all(row["completed"] for row in rows),
            "all_passed": bool(rows) and all(row["passed"] for row in rows),
            "authoritative_within_trusted_fixture_scope": True,
        }
        if persist:
            self.write_json(f"probe-{label}.json", result)
        return result

    def run_negative_control(self, selected: dict) -> dict:
        acceptance_ids = self.acceptance_probe_ids(selected)
        behavior = {p for a in selected["acceptance"] if a.get("kind", "behavior") == "behavior" for p in a["probe_ids"]}
        compatibility = {p for a in selected["acceptance"] if a.get("kind") == "compatibility" for p in a["probe_ids"]}
        if behavior & compatibility:
            raise PolicyConfigurationError("Probe cannot have both negative-control and regression semantics")
        if not acceptance_ids:
            acceptance_ids = {p["id"] for p in self.authority["verification_probes"]["baseline"]}
        evidence = self.run_probes("negative-control", acceptance_ids, persist=False)
        cases = [
            case
            for row in evidence["probes"]
            if row["receipt_valid"] and isinstance(row.get("receipt"), dict)
            for case in row["receipt"].get("cases", [])
        ]
        every_case_completed = bool(cases) and all(case.get("completed") is True for case in cases)
        every_case_rejected = bool(cases) and all(case.get("passed") is False for case in cases)
        negative_passed = evidence["all_completed"] and every_case_completed and all(
            case.get("passed") is (row["probe_id"] not in behavior)
            for row in evidence["probes"] for case in (row.get("receipt") or {}).get("cases", []))
        evidence["negative_control_case_count"] = len(cases)
        evidence["negative_control_all_cases_rejected"] = every_case_rejected
        evidence["negative_control_passed"] = negative_passed
        self.write_json("probe-negative-control.json", evidence)
        return evidence

    def required_probe_ids(self, selected: dict) -> set[str]:
        baseline_ids = {probe["id"] for probe in self.authority["verification_probes"]["baseline"]}
        return baseline_ids | self.acceptance_probe_ids(selected)

    def authority_snapshot(self, label: str) -> dict:
        snapshot = digest_paths(self.workspace, self.policy["authority_paths"])
        if not snapshot["files"]:
            raise PolicyConfigurationError("authority snapshot is empty; configured authority_paths matched no files")
        per_pattern = {pattern: sorted(path for path in snapshot["files"] if matches_any(path, [pattern])) for pattern in self.policy["authority_paths"]}
        empty = [pattern for pattern, paths in per_pattern.items() if not paths]
        if empty:
            raise PolicyConfigurationError(f"authority patterns matched no files: {empty}")
        snapshot["matches"] = per_pattern
        snapshot["controller_verification_sha256"] = self.verification_definition_digest()
        snapshot["digest"] = sha256_json({
            "files": snapshot["files"],
            "controller_verification_sha256": snapshot["controller_verification_sha256"],
        })
        self.write_json(f"authority-snapshot-{label}.json", snapshot)
        return snapshot

    def protected_test_snapshot(self, label: str) -> dict:
        snapshot = digest_paths(self.workspace, self.policy["protected_test_paths"])
        if not snapshot["files"]:
            raise PolicyConfigurationError("protected baseline test snapshot is empty")
        self.write_json(f"protected-tests-{label}.json", snapshot)
        return snapshot


    def workspace_path(self, relative: str) -> Path:
        canonical = safe_relative_path(relative)
        candidate = self.workspace / canonical
        root = self.workspace.resolve()
        resolved = candidate.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"edit path escapes repository workspace: {relative!r}")
        cursor = self.workspace
        for part in Path(canonical).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError(f"edit path traverses symlink: {relative!r}")
        return candidate

    def enforced_forbidden_patterns(self) -> list[str]:
        patterns: list[str] = list(self.goal.get("forbidden_paths", []))
        for rule in self.authority["forbidden"].get("enforced", []):
            if rule.get("kind") == "forbidden_paths":
                patterns.extend(rule.get("patterns", []))
        return patterns

    def check_proposal(self, proposal: list[dict], *, actor: str) -> tuple[bool, list[dict]]:
        """The composed engine supplies the single role-aware shared-core gate."""
        raise NotImplementedError("Use reference_runtime.engine.AutonomousEngine")

    def diff_for(self, proposal: list[dict]) -> str:
        chunks: list[str] = []
        for edit in proposal:
            relative = safe_relative_path(edit["path"])
            path = self.workspace_path(relative)
            old = path.read_text().splitlines(keepends=True) if path.exists() else []
            new = edit["content"].splitlines(keepends=True)
            chunks.extend(difflib.unified_diff(old, new, fromfile=f"a/{relative}", tofile=f"b/{relative}"))
        return "".join(chunks)

    def apply_proposal(self, proposal: list[dict]) -> None:
        for edit in proposal:
            path = self.workspace_path(edit["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(edit["content"])

    def candidate_risk(self, changed_paths: list[str]) -> tuple[str, list[dict]]:
        matched: list[dict] = []
        risk = self.policy["default_risk"]
        for rule in self.policy["risk_rules"]:
            paths = [p for p in changed_paths if matches_any(p, rule["paths"])]
            if paths:
                matched.append({"risk": rule["risk"], "paths": paths})
                if risk_rank(rule["risk"]) > risk_rank(risk):
                    risk = rule["risk"]
        return risk, matched

    def compute_review(
        self,
        *,
        changed_paths: list[str],
        policy_decisions: list[dict],
        authority_before: dict,
        authority_after: dict,
        protected_before: dict,
        protected_after: dict,
        diagnostic_tests: dict,
        candidate_probes: dict,
        negative_control: dict,
        candidate_sha: str,
    ) -> dict:
        gates = self.authority["quality_gates"]
        checks = {
            "authority_snapshot_nonempty": bool(authority_before["files"]) and bool(authority_after["files"]),
            "authority_unchanged": authority_before["digest"] == authority_after["digest"],
            "scope_bounded": all(row["accepted"] for row in policy_decisions),
            "protected_test_files_unchanged": (not gates["protect_baseline_test_files"]) or protected_before["digest"] == protected_after["digest"],
            "negative_control_passed": (not gates["require_negative_control"]) or bool(negative_control.get("negative_control_passed")),
            "controller_probes_green": (not gates["require_controller_probes"]) or candidate_probes["all_passed"],
            "probes_bound_to_candidate_sha": (not gates["bind_probes_to_exact_git_sha"]) or candidate_probes["tested_sha"] == candidate_sha,
            "diagnostic_junit_green": (not gates["require_diagnostic_junit_green"]) or diagnostic_tests["passed"],
        }
        findings = [
            {"kind": name, "severity": "blocking", "message": f"Computed review check failed: {name}"}
            for name, passed in checks.items() if not passed
        ]
        return {
            "schema": 2,
            "role": "reviewer",
            "verdict": "accept" if not findings else "block",
            "candidate_sha": candidate_sha,
            "changed_paths": changed_paths,
            "checks": checks,
            "blocking_findings": findings,
        }

    def build_summary(self, **extra) -> dict:
        seq, tip = EventLog.verify(self.evidence / "events.jsonl")
        summary = {"schema": 2, "reference_contract": self.policy["reference_contract"], "run_id": self.run_id, "label": self.label, "status": self.state["status"], "phase": self.state["phase"], "event_count": seq, "event_tip": tip, "base_sha": self.state["base_sha"], "candidate_sha": self.state["candidate_sha"], "merge_sha": self.state["merge_sha"], "risk": self.state["risk"], "evidence_directory": str(self.evidence), **extra}
        self.write_json("run-summary.json", summary)
        return summary

    def finish(self, status: str, *, phase: str, **extra) -> dict:
        self.state["status"] = status
        self.state["phase"] = phase
        self.event("run-finished", {"status": status, "phase": phase})
        return self.build_summary(**extra)
