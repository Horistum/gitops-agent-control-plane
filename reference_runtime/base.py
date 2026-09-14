from __future__ import annotations

import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from .contracts import (
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
from .executor import LocalFixtureExecutor


class InjectedCrash(RuntimeError):
    pass


class BaseEngine:
    def __init__(self, repository_root: Path, request: dict, output_root: Path, *, run_id: str | None = None):
        self.repo = repository_root.resolve()
        self.request = request
        self.label = request["label"]
        self.output_root = output_root.resolve()
        self.product_source = self.repo / "examples" / "minimal-product"
        self.goal = request["goal"]
        self.policy = load_json(self.repo / "config" / "reference-policy.json")
        validate_goal(self.goal)
        validate_policy(self.policy)
        if request.get("proposal_source") != "trusted-fixture" or self.policy["executor_mode"] != "trusted-fixture-local":
            raise ValueError("standalone runtime refuses non-fixture/untrusted proposal sources without a real sandbox")

        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_id = run_id or f"{stamp}-{self.label}-{sha256_json({'label': self.label, 'ns': time.time_ns()})[:8]}"
        self.run_dir = self.output_root / self.run_id
        self.workspace = self.run_dir / "workspace"
        self.evidence = self.run_dir / "evidence"
        self.evidence.mkdir(parents=True, exist_ok=False)
        shutil.copytree(self.product_source, self.workspace)
        self.events = EventLog(self.evidence / "events.jsonl")
        self.executor = LocalFixtureExecutor(self.policy["test_timeout_seconds"])
        self.authority = self.load_authority()
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
        obj.product_source = obj.repo / "examples" / "minimal-product"
        obj.events = EventLog(obj.evidence / "events.jsonl")
        obj.executor = LocalFixtureExecutor(obj.policy["test_timeout_seconds"])
        obj.state = load_json(obj.evidence / "state.json")
        obj.run_id = obj.state["run_id"]
        obj.authority = obj.load_authority()
        return obj

    def load_authority(self) -> dict:
        authority_dir = self.workspace / ".agent-control"
        value = {
            "roadmap": load_json(authority_dir / "roadmap.json"),
            "quality_gates": load_json(authority_dir / "quality-gates.json"),
            "forbidden": load_json(authority_dir / "forbidden.json"),
            "release_state": load_json(authority_dir / "release-state.json"),
            "authority_text": (authority_dir / "authority.md").read_text(),
            "architecture_text": (authority_dir / "architecture.md").read_text(),
        }
        if value["quality_gates"].get("preserve_baseline_test_identities") is not True:
            raise ValueError("reference requires preserve_baseline_test_identities")
        return value

    def write_json(self, name: str, value: dict | list) -> Path:
        path = self.evidence / name
        path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
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
        junit = self.workspace / "build" / "test-results" / "reference" / "TEST-reference.xml"
        if junit.exists():
            junit.unlink()
        tested_sha = self.git("rev-parse", "HEAD")
        result_exec = self.executor.run([sys.executable, "-S", "ci/run_tests.py"], self.workspace)
        tests = failures = errors = skipped = 0
        identities: list[str] = []
        if junit.is_file():
            suite = ET.parse(junit).getroot()
            tests = int(suite.attrib.get("tests", "0"))
            failures = int(suite.attrib.get("failures", "0"))
            errors = int(suite.attrib.get("errors", "0"))
            skipped = int(suite.attrib.get("skipped", "0"))
            identities = sorted(f"{case.attrib.get('classname')}.{case.attrib.get('name')}" for case in suite.iter("testcase"))
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
            "stdout_sha256": sha256_bytes(result_exec.stdout.encode()),
            "stderr_sha256": sha256_bytes(result_exec.stderr.encode()),
            "executor": {"isolation": result_exec.isolation, "security_sandbox": result_exec.security_sandbox, "trusted_fixture_only": True},
            "passed": result_exec.returncode == 0 and not result_exec.timed_out and failures == 0 and errors == 0,
        }
        self.write_json(f"test-{label}.json", result)
        return result

    def authority_snapshot(self, label: str) -> dict:
        snapshot = digest_paths(self.workspace, self.policy["authority_paths"])
        if not snapshot["files"]:
            raise RuntimeError("authority snapshot is empty; configured authority_paths matched no files")
        per_pattern = {pattern: sorted(path for path in snapshot["files"] if matches_any(path, [pattern])) for pattern in self.policy["authority_paths"]}
        empty = [pattern for pattern, paths in per_pattern.items() if not paths]
        if empty:
            raise RuntimeError(f"authority patterns matched no files: {empty}")
        snapshot["matches"] = per_pattern
        self.write_json(f"authority-snapshot-{label}.json", snapshot)
        return snapshot

    def protected_test_snapshot(self, label: str) -> dict:
        snapshot = digest_paths(self.workspace, self.policy["protected_test_paths"])
        if not snapshot["files"]:
            raise RuntimeError("protected baseline test snapshot is empty")
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
        allowed_patterns = self.policy[f"{actor}_allowed_paths"]
        forbidden = self.enforced_forbidden_patterns()
        decisions = []
        accepted_all = True
        for edit in proposal:
            raw = edit.get("path")
            try:
                canonical = safe_relative_path(raw)
                self.workspace_path(canonical)
                valid = True
                error = None
            except (TypeError, ValueError) as exc:
                canonical = None
                valid = False
                error = str(exc)
            in_allowed = bool(valid and matches_any(canonical, allowed_patterns))
            in_authority = bool(valid and matches_any(canonical, self.policy["authority_paths"]))
            is_forbidden = bool(valid and matches_any(canonical, forbidden))
            accepted = valid and in_allowed and not in_authority and not is_forbidden
            decisions.append({"actor": actor, "path": raw, "canonical_path": canonical, "path_valid": valid, "path_error": error, "allowed_path": in_allowed, "authority_path": in_authority, "forbidden_path": is_forbidden, "accepted": accepted})
            accepted_all = accepted_all and accepted
        return accepted_all, decisions

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

    def baseline_invariants(self, baseline: dict, candidate: dict, protected_before: dict, protected_after: dict) -> dict:
        baseline_ids = set(baseline["test_identities"])
        candidate_ids = set(candidate["test_identities"])
        return {"baseline_identities_preserved": baseline_ids <= candidate_ids, "protected_test_files_unchanged": protected_before["digest"] == protected_after["digest"], "baseline_count": len(baseline_ids), "missing_baseline_identities": sorted(baseline_ids - candidate_ids)}

    def acceptance_test_identities(self, selected: dict) -> set[str]:
        result: set[str] = set()
        for criterion in selected["acceptance"]:
            result.update(criterion.get("test_identities", []))
        return result

    def compute_review(self, *, selected: dict, changed_paths: list[str], policy_decisions: list[dict], authority_before: dict, authority_after: dict, protected_before: dict, protected_after: dict, baseline: dict, candidate_tests: dict, candidate_sha: str) -> dict:
        baseline_checks = self.baseline_invariants(baseline, candidate_tests, protected_before, protected_after)
        required_acceptance = self.acceptance_test_identities(selected)
        observed = set(candidate_tests["test_identities"])
        checks = {
            "authority_snapshot_nonempty": bool(authority_before["files"]) and bool(authority_after["files"]),
            "authority_unchanged": authority_before["digest"] == authority_after["digest"],
            "scope_bounded": all(row["accepted"] for row in policy_decisions),
            "deterministic_tests_green": candidate_tests["passed"],
            "tests_bound_to_candidate_sha": candidate_tests["tested_sha"] == candidate_sha,
            "baseline_identities_preserved": baseline_checks["baseline_identities_preserved"],
            "protected_test_files_unchanged": baseline_checks["protected_test_files_unchanged"],
            "acceptance_covered": required_acceptance <= observed,
            "minimum_candidate_tests_met": candidate_tests["tests"] >= self.policy["minimum_candidate_tests"],
        }
        findings: list[dict] = []
        for name, passed in checks.items():
            if not passed:
                findings.append({"kind": name, "severity": "blocking", "message": f"Computed review check failed: {name}"})
        if baseline_checks["missing_baseline_identities"]:
            findings.append({"kind": "missing-baseline-tests", "severity": "blocking", "message": "Baseline test identities disappeared.", "missing": baseline_checks["missing_baseline_identities"]})
        missing_acceptance = sorted(required_acceptance - observed)
        if missing_acceptance:
            findings.append({"kind": "missing-acceptance-tests", "severity": "blocking", "message": "Required acceptance test identities are missing.", "missing": missing_acceptance})
        return {"schema": 2, "role": "reviewer", "verdict": "accept" if not findings else "block", "candidate_sha": candidate_sha, "changed_paths": changed_paths, "checks": checks, "blocking_findings": findings}

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

    def rollback_uncommitted_candidate(self) -> None:
        self.git("reset", "--hard", "main")
        self.git("checkout", "main")
        self.git("branch", "-D", "reference-candidate", check=False)

    def prepare_merge_effect(self, candidate_sha: str) -> dict:
        request = {"effect": "merge", "candidate_sha": candidate_sha, "base_sha": self.state["base_sha"]}
        request_hash = sha256_json(request)
        effect = {**request, "request_hash": request_hash}
        self.state["pending_effect"] = effect
        self.state["phase"] = "MERGE_PENDING"
        self.state["status"] = "WAITING_EXTERNAL"
        self.write_json("merge-intent.json", {"schema": 2, **effect})
        self.event("effect-intent-persisted", {"kind": "merge", "request_hash": request_hash})
        return effect

    def effect_merge_commits(self, request_hash: str) -> list[str]:
        marker = f"Effect-Id: {request_hash}"
        out = self.git("log", "--all", "--format=%H%x00%B%x00", capture=True)
        chunks = out.split("\x00")
        commits: list[str] = []
        for i in range(0, len(chunks) - 1, 2):
            sha, body = chunks[i].strip(), chunks[i + 1]
            if sha and marker in body:
                commits.append(sha)
        return commits

    def perform_merge_effect(self, effect: dict) -> str:
        existing = self.effect_merge_commits(effect["request_hash"])
        if len(existing) > 1:
            raise RuntimeError("duplicate merge effects detected")
        if existing:
            return existing[0]
        self.git("checkout", "main")
        message = f"Reference simulated merge\n\nEffect-Id: {effect['request_hash']}"
        self.git("merge", "--no-ff", "reference-candidate", "-m", message)
        return self.git("rev-parse", "HEAD")

    def consume_merge_effect(self, effect: dict, merge_sha: str, *, recovered_existing: bool) -> None:
        commits = self.effect_merge_commits(effect["request_hash"])
        if commits != [merge_sha]:
            raise RuntimeError(f"merge effect identity mismatch: {commits} expected {[merge_sha]}")
        self.state["merge_sha"] = merge_sha
        self.state["pending_effect"] = None
        self.state["status"] = "RUNNING"
        self.state["phase"] = "POSTMERGE_VERIFY"
        self.write_json("merge-evidence.json", {"schema": 2, "candidate_sha": effect["candidate_sha"], "merge_sha": merge_sha, "request_hash": effect["request_hash"], "effect_occurrences": len(commits), "recovered_existing_effect": recovered_existing, "method": "local-git-no-ff"})
        self.event("effect-consumed", {"kind": "merge", "request_hash": effect["request_hash"], "merge_sha": merge_sha, "recovered_existing_effect": recovered_existing})
