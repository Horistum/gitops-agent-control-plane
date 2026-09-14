from __future__ import annotations

import argparse
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from .contracts import (
    canonical_json,
    digest_tree,
    load_json,
    matches_any,
    risk_rank,
    sha256_bytes,
    sha256_json,
    validate_goal,
    validate_policy,
)
from .events import EventLog
from .scenarios import EXPECTED_OUTCOME, SUPPORTED, proposal_for


class BaseEngine:
    def __init__(self, repository_root: Path, scenario: str, output_root: Path):
        if scenario not in SUPPORTED:
            raise ValueError(f"unsupported scenario: {scenario}")
        self.repo = repository_root.resolve()
        self.scenario = scenario
        self.output_root = output_root.resolve()
        self.product_source = self.repo / "examples" / "minimal-product"
        self.goal = load_json(self.repo / "examples" / "goal.example.json")
        self.policy = load_json(self.repo / "config" / "reference-policy.json")
        validate_goal(self.goal)
        validate_policy(self.policy)

        stamp = time.strftime("%Y%m%d-%H%M%S")
        suffix = sha256_json({"scenario": scenario, "time_ns": time.time_ns()})[:8]
        self.run_id = f"{stamp}-{scenario}-{suffix}"
        self.run_dir = self.output_root / self.run_id
        self.workspace = self.run_dir / "workspace"
        self.evidence = self.run_dir / "evidence"
        self.evidence.mkdir(parents=True, exist_ok=False)
        shutil.copytree(self.product_source, self.workspace)
        self.events = EventLog(self.evidence / "events.jsonl")
        self.state = {
            "schema": 1,
            "run_id": self.run_id,
            "scenario": scenario,
            "status": "INITIALIZING",
            "base_sha": None,
            "candidate_sha": None,
            "merge_sha": None,
            "risk": self.policy["default_risk"],
            "pending_effect": None,
            "event_tip": None,
        }

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

    def git(self, *args: str, capture: bool = True) -> str:
        p = subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            text=True,
            capture_output=capture,
        )
        if p.returncode:
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
        p = subprocess.run(
            [sys.executable, "ci/run_tests.py"],
            cwd=self.workspace,
            text=True,
            capture_output=True,
        )
        junit = self.workspace / "build" / "test-results" / "reference" / "TEST-reference.xml"
        tests = failures = errors = skipped = 0
        identities: list[str] = []
        if junit.is_file():
            suite = ET.parse(junit).getroot()
            tests = int(suite.attrib.get("tests", "0"))
            failures = int(suite.attrib.get("failures", "0"))
            errors = int(suite.attrib.get("errors", "0"))
            skipped = int(suite.attrib.get("skipped", "0"))
            for case in suite.iter("testcase"):
                identities.append(f"{case.attrib.get('classname')}.{case.attrib.get('name')}")
        result = {
            "schema": 1,
            "label": label,
            "exit_code": p.returncode,
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "test_identities": sorted(identities),
            "stdout_sha256": sha256_bytes(p.stdout.encode()),
            "stderr_sha256": sha256_bytes(p.stderr.encode()),
            "passed": p.returncode == 0 and tests >= self.policy["minimum_tests"] and failures == 0 and errors == 0,
        }
        self.write_json(f"test-{label}.json", result)
        return result

    def authority_snapshot(self) -> dict:
        rows = {}
        for pattern in self.policy["authority_paths"]:
            for path in sorted(self.workspace.glob(pattern)):
                if path.is_file():
                    relative = path.relative_to(self.workspace).as_posix()
                    rows[relative] = sha256_bytes(path.read_bytes())
        snapshot = {"schema": 1, "files": rows, "digest": sha256_json(rows)}
        self.write_json("authority-snapshot.json", snapshot)
        return snapshot

    def role_artifact(self, role: str, verdict: str, summary: str, **extra) -> None:
        value = {
            "schema": 1,
            "role": role,
            "verdict": verdict,
            "summary": summary,
            "scenario": self.scenario,
            **extra,
        }
        self.write_json(f"role-{role}.json", value)

    def check_proposal(self, proposal: list[dict]) -> tuple[bool, list[dict]]:
        decisions = []
        allowed = True
        for edit in proposal:
            path = edit["path"]
            in_authority = matches_any(path, self.policy["authority_paths"])
            in_allowed = matches_any(path, self.policy["allowed_paths"])
            decision = {
                "path": path,
                "authority_path": in_authority,
                "allowed_path": in_allowed,
                "accepted": in_allowed and not in_authority,
            }
            if not decision["accepted"]:
                allowed = False
            decisions.append(decision)
        self.write_json("policy-decision.json", {"schema": 1, "accepted": allowed, "files": decisions})
        return allowed, decisions

    def diff_for(self, proposal: list[dict]) -> str:
        chunks = []
        for edit in proposal:
            path = self.workspace / edit["path"]
            old = path.read_text().splitlines(keepends=True) if path.exists() else []
            new = edit["content"].splitlines(keepends=True)
            chunks.extend(
                difflib.unified_diff(old, new, fromfile=f"a/{edit['path']}", tofile=f"b/{edit['path']}")
            )
        return "".join(chunks)

    def apply_proposal(self, proposal: list[dict]) -> None:
        for edit in proposal:
            path = self.workspace / edit["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(edit["content"])

    def candidate_risk(self, changed_paths: list[str]) -> str:
        if any(matches_any(path, self.policy["critical_paths"]) for path in changed_paths):
            return "high"
        return self.policy["default_risk"]

    def build_summary(self, status: str, **extra) -> dict:
        seq, tip = EventLog.verify(self.evidence / "events.jsonl")
        summary = {
            "schema": 1,
            "reference_contract": self.policy["reference_contract"],
            "run_id": self.run_id,
            "scenario": self.scenario,
            "status": status,
            "expected_status": EXPECTED_OUTCOME[self.scenario],
            "event_count": seq,
            "event_tip": tip,
            "base_sha": self.state["base_sha"],
            "candidate_sha": self.state["candidate_sha"],
            "merge_sha": self.state["merge_sha"],
            "risk": self.state["risk"],
            "evidence_directory": str(self.evidence),
            **extra,
        }
        self.write_json("run-summary.json", summary)
        return summary

    def finish(self, status: str, **extra) -> dict:
        self.state["status"] = status
        self.event("run-finished", {"status": status})
        summary = self.build_summary(status, **extra)
        if status != EXPECTED_OUTCOME[self.scenario]:
            raise RuntimeError(f"scenario {self.scenario} produced {status}, expected {EXPECTED_OUTCOME[self.scenario]}")
        return summary

    def perform_merge(self, candidate_sha: str) -> str:
        self.git("checkout", "main")
        self.git("merge", "--no-ff", "reference-candidate", "-m", "Reference simulated merge")
        merge_sha = self.git("rev-parse", "HEAD")
        self.state["merge_sha"] = merge_sha
        self.write_json(
            "merge-evidence.json",
            {
                "schema": 1,
                "candidate_sha": candidate_sha,
                "merge_sha": merge_sha,
                "method": "local-git-no-ff",
            },
        )
        self.event("merge-completed", {"candidate_sha": candidate_sha, "merge_sha": merge_sha})
        return merge_sha

    def simulate_recovery_then_merge(self, candidate_sha: str) -> str:
        request = {"effect": "merge", "candidate_sha": candidate_sha, "base_sha": self.state["base_sha"]}
        request_hash = sha256_json(request)
        self.state["pending_effect"] = {"kind": "merge", "request_hash": request_hash}
        self.write_json("merge-intent.json", {"schema": 1, **request, "request_hash": request_hash})
        self.event("effect-intent-persisted", {"kind": "merge", "request_hash": request_hash})

        reloaded = load_json(self.evidence / "state.json")
        intent = load_json(self.evidence / "merge-intent.json")
        recovered = (
            reloaded["pending_effect"]["request_hash"] == intent["request_hash"] == request_hash
            and reloaded["candidate_sha"] == candidate_sha
        )
        if not recovered:
            raise RuntimeError("recovery identity mismatch")
        self.write_json(
            "recovery.json",
            {
                "schema": 1,
                "simulated_restart": True,
                "recovered_pending_effect": True,
                "request_hash": request_hash,
                "duplicate_effect_prevented": True,
            },
        )
        self.event("recovered-pending-effect", {"request_hash": request_hash})
        merge_sha = self.perform_merge(candidate_sha)
        self.state["pending_effect"] = None
        self.event("effect-consumed", {"kind": "merge", "request_hash": request_hash, "merge_sha": merge_sha})
        return merge_sha
