from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .adapters import LocalGitEffectAdapter, LocalVerificationAdapter
from .base import BaseEngine, InjectedCrash, PolicyConfigurationError
from .contracts import (
    CORE_CONTRACT,
    REFERENCE_CONTRACT,
    RUNTIME_PROFILE,
    VERIFICATION_PROFILE,
    digest_tree,
    load_json,
    risk_rank,
    sha256_bytes,
    sha256_json,
    validate_contract_set,
)
from .events import EventLog
from .scenarios import build_request


TERMINAL_STATUSES = {"COMPLETED", "BLOCKED_POLICY", "FAILED_VERIFICATION"}


class AutonomousEngine(BaseEngine):
    """Bounded autonomous work/reconciliation loop for the standalone reference."""

    def __init__(
        self,
        repository_root: Path,
        request: dict,
        output_root: Path,
        *,
        run_id: str | None = None,
    ):
        super().__init__(repository_root, request, output_root, run_id=run_id)
        self._install_v7_runtime()
        self._initialize_v7_state()

    def _install_v7_runtime(self) -> None:
        self.contract_set = load_json(self.repo / "config" / "contract-set.json")
        validate_contract_set(self.contract_set)
        self.role_protocols = load_json(self.repo / "config" / "role-protocols.json")
        self.authority_model = load_json(self.workspace / ".agent-control" / "authority-model.json")
        raw_executor = self.executor
        self.verification_adapter = LocalVerificationAdapter(raw_executor)
        self.executor = self.verification_adapter
        self.effect_adapter = LocalGitEffectAdapter(self.git)
        if self.verification_adapter.profile != RUNTIME_PROFILE or self.effect_adapter.profile != RUNTIME_PROFILE:
            raise PolicyConfigurationError("runtime adapter profile mismatch")
        if set(self.role_protocols.get("roles", {})) != {
            "discovery", "architect", "developer", "test-designer", "tester", "reviewer"
        }:
            raise PolicyConfigurationError("role protocol set invalid")

    def _initialize_v7_state(self) -> None:
        release = self.authority.get("release_state", {}) if not self.authority_error else {}
        self.state.update({
            "goal_status": "ACTIVE",
            "current_item": None,
            "cycle": 0,
            "attempt": 0,
            "completed_items": list(release.get("completed", [])),
            "pending_decision": None,
            "current_candidate_branch": None,
        })
        self.save_state()
        self.write_json("contract-set.json", self.contract_set)
        self._write_control_loop()

    @classmethod
    def resume_engine(cls, repository_root: Path, run_dir: Path) -> "AutonomousEngine":
        base = BaseEngine.resume_from(repository_root, run_dir)
        engine = cls.__new__(cls)
        engine.__dict__.update(base.__dict__)
        engine._install_v7_runtime()
        return engine

    def _role(
        self,
        role: str,
        verdict: str,
        summary: str,
        *,
        item: str | None,
        iteration: int,
        input_refs: list[str],
        output: dict,
    ) -> None:
        protocol = self.role_protocols["roles"][role]
        artifact = {
            "schema": 3,
            "protocol": f"{CORE_CONTRACT}/role/{role}/v1",
            "role": role,
            "item": item,
            "iteration": iteration,
            "verdict": verdict,
            "summary": summary,
            "input_refs": input_refs,
            "output": output,
            "product_write_power": protocol["product_write_power"],
            "effect_power": protocol["effect_power"],
        }
        self.write_json(f"role-{role}.json", artifact)
        if item:
            self.write_json(
                f"role-{role}-{item.lower()}-attempt-{iteration:02d}.json",
                artifact,
            )

    def _control_loop_value(self) -> dict:
        path = self.evidence / "control-loop.json"
        if path.is_file():
            value = json.loads(path.read_text())
            if isinstance(value.get("cycles"), list):
                return value
        return {
            "schema": 1,
            "reference_contract": REFERENCE_CONTRACT,
            "core_contract": CORE_CONTRACT,
            "objective": self.goal["objective"],
            "cycles": [],
            "completed_items": list(self.state.get("completed_items", [])),
            "goal_satisfied": False,
        }

    def _write_control_loop(self) -> None:
        value = self._control_loop_value()
        value["completed_items"] = list(self.state.get("completed_items", []))
        value["goal_satisfied"] = self.state.get("goal_status") == "SATISFIED"
        self.write_json("control-loop.json", value)

    def _append_cycle(self, item: str, attempts: list[dict], result: str) -> None:
        value = self._control_loop_value()
        row = {
            "cycle": self.state["cycle"],
            "item": item,
            "attempts": attempts,
            "result": result,
        }
        if (
            value["cycles"]
            and value["cycles"][-1].get("cycle") == self.state["cycle"]
            and value["cycles"][-1].get("item") == item
        ):
            existing = value["cycles"][-1]
            seen = {attempt["attempt"] for attempt in existing.get("attempts", [])}
            existing.setdefault("attempts", []).extend(
                attempt for attempt in attempts if attempt["attempt"] not in seen
            )
            existing["result"] = result
        else:
            value["cycles"].append(row)
        value["completed_items"] = list(self.state.get("completed_items", []))
        value["goal_satisfied"] = self.state.get("goal_status") == "SATISFIED"
        self.write_json("control-loop.json", value)

    def eligible_items(self) -> list[dict]:
        completed = set(self.authority["release_state"].get("completed", []))
        requested = set(self.goal["items"])
        return [
            item
            for item in self.authority["roadmap"]["items"]
            if item["id"] in requested
            and item["id"] not in completed
            and item.get("status") == "ready"
            and set(item.get("dependencies", [])) <= completed
        ]

    def _roadmap_item(self, item_id: str) -> dict:
        item = next((x for x in self.authority["roadmap"]["items"] if x["id"] == item_id), None)
        if item is None:
            raise PolicyConfigurationError(f"roadmap item missing during resume: {item_id}")
        return item

    def _goal_evaluation(self) -> dict:
        completed = set(self.authority["release_state"].get("completed", []))
        requested = list(self.goal["items"])
        remaining = [item for item in requested if item not in completed]
        eligible = [item["id"] for item in self.eligible_items()]
        by_id = {item["id"]: item for item in self.authority["roadmap"]["items"]}
        blocked: dict[str, list[str]] = {}
        for item_id in remaining:
            item = by_id.get(item_id)
            if item:
                missing = sorted(set(item.get("dependencies", [])) - completed)
                if missing:
                    blocked[item_id] = missing
        value = {
            "schema": 1,
            "objective": self.goal["objective"],
            "requested_items": requested,
            "completed_items": [item for item in requested if item in completed],
            "remaining_items": remaining,
            "eligible_items": eligible,
            "blocked_dependencies": blocked,
            "satisfied": not remaining,
            "cycle": self.state["cycle"],
            "success_condition_semantics": "verified_projection",
        }
        self.write_json("goal-evaluation.json", value)
        self.write_json(f"goal-evaluation-cycle-{self.state['cycle']:02d}.json", value)
        return value

    def _completed_acceptance_probe_ids(self) -> set[str]:
        completed = set(self.authority["release_state"].get("completed", []))
        result: set[str] = set()
        for item in self.authority["roadmap"]["items"]:
            if item["id"] in completed:
                result.update(self.acceptance_probe_ids(item))
        return result

    def required_probe_ids(self, selected: dict) -> set[str]:
        baseline = {probe["id"] for probe in self.authority["verification_probes"]["baseline"]}
        return baseline | self._completed_acceptance_probe_ids() | self.acceptance_probe_ids(selected)

    def _archive(self, generic_name: str, specific_name: str) -> None:
        path = self.evidence / generic_name
        if path.is_file():
            self.write_json(specific_name, json.loads(path.read_text()))

    def _discard_candidate_branch(self) -> None:
        branch = self.state.get("current_candidate_branch")
        self.git("checkout", "main", check=False)
        if branch:
            self.git("branch", "-D", branch, check=False)
        self.state["candidate_sha"] = None
        self.state["merge_sha"] = None
        self.state["pending_effect"] = None
        self.state["current_candidate_branch"] = None
        self.save_state()

    def _prepare_merge_effect(self, candidate_sha: str) -> dict:
        branch = self.state["current_candidate_branch"]
        request = {
            "effect": "merge",
            "candidate_sha": candidate_sha,
            "base_sha": self.state["base_sha"],
            "candidate_branch": branch,
        }
        effect = {**request, "request_hash": sha256_json(request)}
        self.state["pending_effect"] = effect
        self.state["phase"] = "MERGE_PENDING"
        self.state["status"] = "WAITING_EXTERNAL"
        merge_intent = {"schema": 3, **effect}
        self.write_json("merge-intent.json", merge_intent)
        self.write_json(
            f"merge-intent-{self.state['current_item'].lower()}.json",
            merge_intent,
        )
        self.event("effect-intent-persisted", {
            "kind": "merge",
            "request_hash": effect["request_hash"],
            "candidate_branch": branch,
        })
        return effect

    def _find_merge_effects(self, request_hash: str) -> list[str]:
        return self.effect_adapter.find_trailer_effect("Effect-Id", request_hash)

    def _perform_merge_effect(self, effect: dict) -> str:
        existing = self._find_merge_effects(effect["request_hash"])
        if len(existing) > 1:
            raise RuntimeError("duplicate merge effects detected")
        if existing:
            return existing[0]
        message = (
            f"Reference merge for {self.state['current_item']}\n\n"
            f"Effect-Id: {effect['request_hash']}"
        )
        return self.effect_adapter.merge(effect["candidate_branch"], message)

    def _consume_merge_effect(
        self,
        effect: dict,
        merge_sha: str,
        *,
        recovered_existing: bool,
    ) -> None:
        commits = self._find_merge_effects(effect["request_hash"])
        if commits != [merge_sha]:
            raise RuntimeError(f"merge effect identity mismatch: {commits} expected {[merge_sha]}")
        self.state["merge_sha"] = merge_sha
        self.state["pending_effect"] = None
        self.state["status"] = "RUNNING"
        self.state["phase"] = "POSTMERGE_VERIFY"
        merge_evidence = {
            "schema": 2,
            "candidate_sha": effect["candidate_sha"],
            "merge_sha": merge_sha,
            "request_hash": effect["request_hash"],
            "effect_occurrences": len(commits),
            "recovered_existing_effect": recovered_existing,
            "method": "runtime-profile-git-merge",
        }
        self.write_json("merge-evidence.json", merge_evidence)
        self.write_json(
            f"merge-evidence-{self.state['current_item'].lower()}.json",
            merge_evidence,
        )
        self.event("effect-consumed", {
            "kind": "merge",
            "request_hash": effect["request_hash"],
            "merge_sha": merge_sha,
            "recovered_existing_effect": recovered_existing,
        })

    def _record_release_state(self, selected: dict, verified_merge_sha: str) -> str:
        release_path = self.workspace / ".agent-control" / "release-state.json"
        release = json.loads(release_path.read_text())
        if selected["id"] not in release["completed"]:
            release["completed"].append(selected["id"])
            release["history"].append({
                "item": selected["id"],
                "verified_merge_sha": verified_merge_sha,
                "recorded_by": "controller",
            })
            release_path.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")

        control_state_id = sha256_json({
            "item": selected["id"],
            "verified_merge_sha": verified_merge_sha,
            "completed": release["completed"],
        })
        existing = self.effect_adapter.find_trailer_effect("Control-State-Id", control_state_id)
        if len(existing) > 1:
            raise RuntimeError("duplicate control-state effects detected")
        if existing:
            release_commit = existing[0]
        else:
            message = (
                f"Record verified completion of {selected['id']}\n\n"
                f"Control-State-Id: {control_state_id}"
            )
            release_commit = self.effect_adapter.commit_control_state(
                [".agent-control/release-state.json"],
                message,
            )
        self.write_json(f"release-transition-{selected['id'].lower()}.json", {
            "schema": 1,
            "item": selected["id"],
            "verified_merge_sha": verified_merge_sha,
            "control_state_id": control_state_id,
            "release_state_sha": release_commit,
        })
        self.authority = self.load_authority()
        self.state["completed_items"] = list(self.authority["release_state"]["completed"])
        self.state["base_sha"] = release_commit
        self.event("release-state-transition", {
            "item": selected["id"],
            "verified_merge_sha": verified_merge_sha,
            "release_state_sha": release_commit,
            "control_state_id": control_state_id,
        })
        return release_commit

    def _postmerge_verify_and_record(self, selected: dict) -> dict | None:
        self.transition("POSTMERGE_VERIFY")
        merge_sha = self.state["merge_sha"]
        post_tests = self.run_tests("postmerge")
        post_probes = self.run_probes("postmerge", self.required_probe_ids(selected))
        self._archive(
            "test-postmerge.json",
            f"test-postmerge-{selected['id'].lower()}.json",
        )
        self._archive(
            "probe-postmerge.json",
            f"probe-postmerge-{selected['id'].lower()}.json",
        )
        gates = self.authority["quality_gates"]
        passed = (
            post_probes["all_passed"]
            and ((not gates["bind_probes_to_exact_git_sha"]) or post_probes["tested_sha"] == merge_sha)
            and ((not gates["require_diagnostic_junit_green"]) or post_tests["passed"])
        )
        evidence = {
            "schema": 2,
            "merge_sha": merge_sha,
            "tested_sha": post_probes["tested_sha"],
            "passed": passed,
            "controller_probes_passed": post_probes["all_passed"],
            "diagnostic_junit_passed": post_tests["passed"],
        }
        self.write_json("postmerge-evidence.json", evidence)
        self.write_json(f"postmerge-evidence-{selected['id'].lower()}.json", evidence)
        if not passed:
            self.event("postmerge-verification-failed", {"item": selected["id"], "merge_sha": merge_sha})
            self.state["goal_status"] = "BLOCKED"
            return self.finish(
                "FAILED_VERIFICATION",
                phase="FAILED_VERIFICATION",
                reason="post-merge verification failed",
            )
        self.event("postmerge-verified", {
            "item": selected["id"],
            "merge_sha": merge_sha,
            "probe_ids": post_probes["probe_ids"],
        })
        self._record_release_state(selected, merge_sha)
        return None

    def _write_feedback(self, selected: dict, attempt: int, review: dict, *, source: str) -> dict:
        feedback = {
            "schema": 1,
            "item": selected["id"],
            "attempt": attempt,
            "route": "developer-repair",
            "blocking_findings": review.get("blocking_findings", []) or [{
                "kind": source,
                "severity": "blocking",
                "message": source,
            }],
            "candidate_sha": self.state["candidate_sha"],
        }
        self.write_json(
            f"feedback-{selected['id'].lower()}-attempt-{attempt:02d}.json",
            feedback,
        )
        self.event("feedback-created", {
            "item": selected["id"],
            "attempt": attempt,
            "source": source,
        })
        return feedback

    def _pause(self, *, phase: str, **extra) -> dict:
        self.state["status"] = "NEEDS_DECISION"
        self.state["phase"] = phase
        self.event("run-paused", {
            "status": "NEEDS_DECISION",
            "phase": phase,
            "goal_status": self.state.get("goal_status"),
        })
        self._write_control_loop()
        return self.build_summary(**extra)

    def _human_pause(
        self,
        selected: dict,
        attempt: int,
        risk: str,
        reasons: list[str],
    ) -> dict:
        human = {
            "schema": 3,
            "required": True,
            "item": selected["id"],
            "candidate_sha": self.state["candidate_sha"],
            "candidate_branch": self.state["current_candidate_branch"],
            "attempt": attempt,
            "risk": risk,
            "reasons": reasons,
            "allowed_actions": ["approve", "reject", "request_changes"],
            "decision": None,
            "decided_by": None,
        }
        self.state["pending_decision"] = human
        self.write_json("human-decision.json", human)
        self.write_json(
            f"human-decision-{selected['id'].lower()}-attempt-{attempt:02d}.json",
            human,
        )
        self.event("human-decision-required", {
            "item": selected["id"],
            "attempt": attempt,
            "risk": risk,
            "reasons": reasons,
        })
        return self._pause(
            phase="AWAITING_DECISION",
            risk_decision=load_json(self.evidence / "risk-decision.json"),
            goal_satisfied=False,
        )

    def _attempt_work(self, selected: dict, attempt: int, prior_feedback: dict | None) -> tuple[str, dict | None]:
        item_id = selected["id"]
        self.state["attempt"] = attempt
        self.state["current_item"] = item_id
        self.save_state()

        catalog = self.request["work_catalog"].get(item_id, [])
        if attempt > len(catalog):
            return "EXHAUSTED", prior_feedback
        work = catalog[attempt - 1]
        developer = work["developer_proposal"]
        tester = work["tester_proposal"]

        self.transition("PLANNING")
        plan = {
            "schema": 3,
            "item": item_id,
            "attempt": attempt,
            "objective": selected["goal"],
            "acceptance": selected["acceptance"],
            "developer_working_set": self.policy["developer_allowed_paths"],
            "tester_working_set": self.policy["tester_allowed_paths"],
            "non_goals": selected["non_goals"],
            "verification": [
                "baseline regression probes",
                "case-level acceptance negative control",
                "candidate probes on exact candidate SHA",
                "diagnostic JUnit",
                "computed review",
                "post-merge probes including completed-item regressions",
            ],
        }
        self.write_json("plan.json", plan)
        self.write_json(f"plan-{item_id.lower()}-attempt-{attempt:02d}.json", plan)
        self._role(
            "architect",
            "accept",
            "Bounded plan created from machine authority and prior feedback.",
            item=item_id,
            iteration=attempt,
            input_refs=["goal.json", "roadmap.json"] + (
                [f"feedback-{item_id.lower()}-attempt-{attempt-1:02d}.json"] if prior_feedback else []
            ),
            output={"plan_sha256": sha256_json(plan)},
        )

        self._role(
            "developer",
            "propose",
            "Developer produced an implementation proposal within its declared role protocol.",
            item=item_id,
            iteration=attempt,
            input_refs=["plan.json"],
            output={"changed_paths": [row["path"] for row in developer]},
        )
        self._role(
            "test-designer",
            "propose",
            "Test designer produced supplemental diagnostic tests.",
            item=item_id,
            iteration=attempt,
            input_refs=["plan.json"],
            output={"changed_paths": [row["path"] for row in tester]},
        )

        self.transition("PROPOSAL_GATES")
        dev_ok, dev_decisions = self.check_proposal(developer, actor="developer")
        tester_ok, tester_decisions = self.check_proposal(tester, actor="tester")
        decisions = dev_decisions + tester_decisions
        policy_value = {"schema": 2, "accepted": dev_ok and tester_ok, "files": decisions}
        self.write_json("policy-decision.json", policy_value)
        self.write_json(
            f"policy-decision-{item_id.lower()}-attempt-{attempt:02d}.json",
            policy_value,
        )
        if not dev_ok or not tester_ok:
            self.event("proposal-blocked", {"item": item_id, "attempt": attempt, "decisions": decisions})
            return "BLOCKED_POLICY", {
                "reason": "proposal violated write authority",
                "unauthorized_paths": [row["path"] for row in decisions if not row["accepted"]],
            }

        combined_diff = self.diff_for(developer) + self.diff_for(tester)
        changed = [row["canonical_path"] for row in decisions]
        proposal = {
            "schema": 2,
            "developer_edits": [
                {"path": row["path"], "content_sha256": sha256_bytes(row["content"].encode())}
                for row in developer
            ],
            "tester_edits": [
                {"path": row["path"], "content_sha256": sha256_bytes(row["content"].encode())}
                for row in tester
            ],
            "patch_sha256": sha256_bytes(combined_diff.encode()),
        }
        self.write_json("proposal.json", proposal)
        self.write_json(f"proposal-{item_id.lower()}-attempt-{attempt:02d}.json", proposal)
        (self.evidence / "candidate.patch").write_text(combined_diff)

        if len(changed) > self.policy["max_changed_files"] or len(combined_diff.encode()) > self.policy["max_patch_bytes"]:
            self.event("budget-blocked", {
                "item": item_id,
                "attempt": attempt,
                "changed_files": len(changed),
                "max_changed_files": self.policy["max_changed_files"],
                "patch_bytes": len(combined_diff.encode()),
                "max_patch_bytes": self.policy["max_patch_bytes"],
            })
            return "BLOCKED_POLICY", {"reason": "change budget exceeded before write"}

        risk, risk_matches = self.candidate_risk(changed)
        self.state["risk"] = risk
        self.save_state()
        if risk_rank(risk) > risk_rank(self.goal["risk_ceiling"]):
            self.event("risk-ceiling-exceeded", {
                "item": item_id,
                "risk": risk,
                "ceiling": self.goal["risk_ceiling"],
            })
            return "BLOCKED_POLICY", {"reason": "goal risk ceiling exceeded before write"}

        base_sha = self.git("rev-parse", "main")
        self.state["base_sha"] = base_sha
        authority_before = self.authority_snapshot("baseline")
        protected_before = self.protected_test_snapshot("baseline")

        self.transition("CANDIDATE_APPLY")
        branch = f"candidate-{item_id.lower()}-attempt-{attempt:02d}"
        self.git("checkout", "main")
        self.git("branch", "-D", branch, check=False)
        self.git("checkout", "-b", branch)
        self.state["current_candidate_branch"] = branch
        self.apply_proposal(developer)
        self.apply_proposal(tester)
        authority_after = self.authority_snapshot("candidate")
        protected_after = self.protected_test_snapshot("candidate")
        if authority_after["digest"] != authority_before["digest"]:
            self.git("reset", "--hard", base_sha)
            self._discard_candidate_branch()
            self.event("authority-drift-blocked", {"item": item_id})
            return "BLOCKED_POLICY", {"reason": "authority changed during candidate application"}
        if protected_after["digest"] != protected_before["digest"]:
            self.git("reset", "--hard", base_sha)
            self._discard_candidate_branch()
            self.event("protected-tests-drift-blocked", {"item": item_id})
            return "BLOCKED_POLICY", {"reason": "protected baseline tests changed"}

        self.transition("CANDIDATE_COMMIT")
        self.git("add", ".")
        self.git("commit", "-m", f"Candidate for {item_id} attempt {attempt}")
        candidate_sha = self.git("rev-parse", "HEAD")
        self.state["candidate_sha"] = candidate_sha
        self.save_state()

        candidate_evidence = {
            "schema": 2,
            "base_sha": base_sha,
            "candidate_sha": candidate_sha,
            "changed_paths": changed,
            "patch_sha256": proposal["patch_sha256"],
            "tree_digest": digest_tree(self.workspace),
            "authority_snapshot_before": authority_before["digest"],
            "authority_snapshot_candidate": authority_after["digest"],
            "protected_tests_before": protected_before["digest"],
            "protected_tests_candidate": protected_after["digest"],
        }
        self.write_json("candidate-evidence.json", candidate_evidence)
        self.write_json(
            f"candidate-evidence-{item_id.lower()}-attempt-{attempt:02d}.json",
            candidate_evidence,
        )
        self.event("candidate-created", {
            "item": item_id,
            "attempt": attempt,
            "candidate_sha": candidate_sha,
            "changed_paths": changed,
        })

        self.transition("CANDIDATE_VERIFY")
        tests = self.run_tests("candidate")
        probes = self.run_probes("candidate", self.required_probe_ids(selected))
        self._archive(
            "test-candidate.json",
            f"test-candidate-{item_id.lower()}-attempt-{attempt:02d}.json",
        )
        self._archive(
            "probe-candidate.json",
            f"probe-candidate-{item_id.lower()}-attempt-{attempt:02d}.json",
        )
        self._role(
            "tester",
            "accept" if probes["all_passed"] else "block",
            "Controller-owned verification evidence assessed by tester role.",
            item=item_id,
            iteration=attempt,
            input_refs=["probe-candidate.json", "test-candidate.json"],
            output={
                "tested_sha": probes["tested_sha"],
                "probe_ids": probes["probe_ids"],
                "diagnostic_junit_passed": tests["passed"],
            },
        )

        self.transition("REVIEW")
        negative = load_json(self.evidence / "probe-negative-control.json")
        review = self.compute_review(
            changed_paths=changed,
            policy_decisions=decisions,
            authority_before=authority_before,
            authority_after=authority_after,
            protected_before=protected_before,
            protected_after=protected_after,
            diagnostic_tests=tests,
            candidate_probes=probes,
            negative_control=negative,
            candidate_sha=candidate_sha,
        )
        self.write_json("review.json", review)
        self.write_json(f"review-{item_id.lower()}-attempt-{attempt:02d}.json", review)
        self._role(
            "reviewer",
            review["verdict"],
            "Reviewer projection derived from controller evidence.",
            item=item_id,
            iteration=attempt,
            input_refs=[
                "policy-decision.json",
                "probe-candidate.json",
                "candidate-evidence.json",
            ],
            output={
                "checks": review["checks"],
                "blocking_findings": review["blocking_findings"],
            },
        )
        if review["verdict"] != "accept":
            feedback = self._write_feedback(selected, attempt, review, source="verification")
            self._discard_candidate_branch()
            return "REPAIR_REQUESTED", feedback

        self.transition("RISK_GATE")
        human_gate = risk_rank(risk) >= risk_rank(self.policy["human_gate_at"])
        auto_ceiling = self.goal["auto_merge_ceiling"]
        auto_allowed = auto_ceiling != "none" and risk_rank(risk) <= risk_rank(auto_ceiling)
        risk_decision = {
            "schema": 2,
            "risk": risk,
            "matched_rules": risk_matches,
            "human_gate_required": human_gate,
            "auto_merge_ceiling": auto_ceiling,
            "auto_merge_allowed": auto_allowed and not human_gate,
            "decision_reasons": (
                (["HUMAN_GATE_THRESHOLD"] if human_gate else [])
                + (["AUTO_MERGE_CEILING"] if not auto_allowed else [])
            ),
        }
        self.write_json("risk-decision.json", risk_decision)
        self.write_json(
            f"risk-decision-{item_id.lower()}-attempt-{attempt:02d}.json",
            risk_decision,
        )
        if human_gate or not auto_allowed:
            return "NEEDS_DECISION", self._human_pause(
                selected,
                attempt,
                risk,
                risk_decision["decision_reasons"],
            )

        effect = self._prepare_merge_effect(candidate_sha)
        merge_sha = self._perform_merge_effect(effect)
        if self.request.get("fault_injection") == "after-merge-effect-before-receipt":
            self.write_json("fault-injection.json", {
                "schema": 1,
                "point": self.request["fault_injection"],
                "effect_sha": merge_sha,
            })
            raise InjectedCrash(
                f"injected crash after merge effect {merge_sha} before receipt"
            )
        self._consume_merge_effect(effect, merge_sha, recovered_existing=False)
        terminal = self._postmerge_verify_and_record(selected)
        if terminal is not None:
            return "TERMINAL", terminal
        return "COMPLETED", None

    def _run_selected_item(self, selected: dict, *, start_attempt: int = 1) -> dict | None:
        item_id = selected["id"]
        attempts_evidence: list[dict] = []
        catalog = self.request["work_catalog"].get(item_id, [])
        allowed_attempts = min(
            self.goal["autonomy"]["max_attempts_per_item"],
            self.policy["max_attempts_per_item"],
        )
        prior_feedback = None
        if start_attempt > 1:
            previous = self.evidence / f"feedback-{item_id.lower()}-attempt-{start_attempt-1:02d}.json"
            if previous.is_file():
                prior_feedback = json.loads(previous.read_text())

        for attempt in range(start_attempt, allowed_attempts + 1):
            if attempt > len(catalog):
                self._append_cycle(item_id, attempts_evidence, "FAILED_VERIFICATION")
                self.state["goal_status"] = "BLOCKED"
                return self.finish(
                    "FAILED_VERIFICATION",
                    phase="FAILED_VERIFICATION",
                    reason="bounded work catalog exhausted before a verified candidate",
                )
            result, detail = self._attempt_work(selected, attempt, prior_feedback)
            attempts_evidence.append({"attempt": attempt, "result": result})

            if result == "COMPLETED":
                self._append_cycle(item_id, attempts_evidence, "COMPLETED")
                return None
            if result == "REPAIR_REQUESTED":
                prior_feedback = detail
                continue
            if result == "NEEDS_DECISION":
                self._append_cycle(item_id, attempts_evidence, "NEEDS_DECISION")
                return detail
            if result == "TERMINAL":
                self._append_cycle(item_id, attempts_evidence, self.state["status"])
                return detail
            if result == "BLOCKED_POLICY":
                self._append_cycle(item_id, attempts_evidence, "BLOCKED_POLICY")
                self.state["goal_status"] = "BLOCKED"
                return self.finish(
                    "BLOCKED_POLICY",
                    phase="BLOCKED_POLICY",
                    **(detail or {}),
                )
            if result == "EXHAUSTED":
                break

        self._append_cycle(item_id, attempts_evidence, "FAILED_VERIFICATION")
        self.state["goal_status"] = "BLOCKED"
        return self.finish(
            "FAILED_VERIFICATION",
            phase="FAILED_VERIFICATION",
            reason="autonomy attempt budget exhausted",
        )

    def _reconcile_loop(self) -> dict:
        max_cycles = min(
            self.goal["autonomy"]["max_cycles"],
            self.policy["max_cycles"],
        )
        while True:
            self.transition("RECONCILE")
            self.authority = self.load_authority()
            self.state["completed_items"] = list(self.authority["release_state"]["completed"])
            evaluation = self._goal_evaluation()
            if evaluation["satisfied"]:
                self.state["goal_status"] = "SATISFIED"
                self.state["current_item"] = None
                self.state["attempt"] = 0
                self._write_control_loop()
                self.event("goal-satisfied", {
                    "completed_items": self.state["completed_items"],
                    "cycle": self.state["cycle"],
                })
                return self.finish(
                    "COMPLETED",
                    phase="GOAL_COMPLETED",
                    goal_satisfied=True,
                )

            if self.state["cycle"] >= max_cycles:
                self.state["goal_status"] = "BLOCKED"
                self._write_control_loop()
                return self.finish(
                    "BLOCKED_POLICY",
                    phase="BLOCKED_POLICY",
                    reason="autonomy cycle budget exhausted",
                    goal_satisfied=False,
                )

            eligible = self.eligible_items()
            if not eligible:
                self.state["goal_status"] = "AUTHORITY_EXHAUSTED"
                self._write_control_loop()
                self.event("authority-exhausted", {
                    "remaining_items": evaluation["remaining_items"],
                    "blocked_dependencies": evaluation["blocked_dependencies"],
                })
                return self.finish(
                    "BLOCKED_POLICY",
                    phase="BLOCKED_POLICY",
                    reason="no dependency-ready authorized work remains",
                    goal_satisfied=False,
                )

            selected = eligible[0]
            self.state["cycle"] += 1
            self.state["current_item"] = selected["id"]
            self.state["attempt"] = 0
            self.save_state()
            self.transition("DISCOVERY")
            self._role(
                "discovery",
                "accept",
                "Selected the first dependency-ready requested roadmap item.",
                item=selected["id"],
                iteration=0,
                input_refs=["goal.json", "goal-evaluation.json", ".agent-control/roadmap.json", ".agent-control/release-state.json"],
                output={
                    "eligible_items": [item["id"] for item in eligible],
                    "selected_item": selected["id"],
                    "selection_reason": "dependency-ready and requested by enforced goal intent",
                },
            )
            self.event("item-selected", {
                "cycle": self.state["cycle"],
                "item": selected["id"],
                "eligible": [item["id"] for item in eligible],
            })

            self.transition("BASELINE_VERIFY")
            baseline_tests = self.run_tests("baseline")
            self._archive(
                "test-baseline.json",
                f"test-baseline-{selected['id'].lower()}-cycle-{self.state['cycle']:02d}.json",
            )
            if (
                not baseline_tests["passed"]
                or baseline_tests["tests"] < self.policy["minimum_baseline_tests"]
            ):
                self.state["goal_status"] = "BLOCKED"
                return self.finish(
                    "FAILED_VERIFICATION",
                    phase="FAILED_VERIFICATION",
                    reason="baseline diagnostic verification failed",
                )
            regression_ids = (
                {probe["id"] for probe in self.authority["verification_probes"]["baseline"]}
                | self._completed_acceptance_probe_ids()
            )
            baseline_probes = self.run_probes("baseline", regression_ids)
            self._archive(
                "probe-baseline.json",
                f"probe-baseline-{selected['id'].lower()}-cycle-{self.state['cycle']:02d}.json",
            )
            if not baseline_probes["all_passed"]:
                self.state["goal_status"] = "BLOCKED"
                return self.finish(
                    "FAILED_VERIFICATION",
                    phase="FAILED_VERIFICATION",
                    reason="completed-product regression probes failed",
                )
            negative = self.run_negative_control(selected)
            self.write_json(
                f"probe-negative-control-{selected['id'].lower()}-cycle-{self.state['cycle']:02d}.json",
                negative,
            )
            if not negative["negative_control_passed"]:
                self.state["goal_status"] = "BLOCKED"
                return self.finish(
                    "BLOCKED_POLICY",
                    phase="BLOCKED_POLICY",
                    reason="acceptance negative control failed on current baseline",
                )

            terminal = self._run_selected_item(selected)
            if terminal is not None:
                return terminal

    def run(self) -> dict:
        try:
            if self.authority_error:
                raise PolicyConfigurationError(self.authority_error)
            self.transition("INITIALIZING")
            base_sha = self.init_git()
            self.state["base_sha"] = base_sha
            self.authority = self.load_authority()
            self.state["completed_items"] = list(self.authority["release_state"]["completed"])
            self.save_state()
            return self._reconcile_loop()
        except PolicyConfigurationError as exc:
            self.state["goal_status"] = "BLOCKED"
            self.event("policy-configuration-blocked", {"reason": str(exc)})
            return self.finish(
                "BLOCKED_POLICY",
                phase="BLOCKED_POLICY",
                reason=f"policy configuration invalid: {exc}",
                goal_satisfied=False,
            )

    def apply_human_decision(self, decision: str, decided_by: str) -> dict:
        if decision not in {"approve", "reject", "request_changes"}:
            raise ValueError("decision must be approve, reject, or request_changes")
        pending = self.state.get("pending_decision")
        if self.state.get("phase") != "AWAITING_DECISION" or not isinstance(pending, dict):
            raise RuntimeError("run is not awaiting a human decision")
        selected = self._roadmap_item(pending["item"])
        if pending["candidate_sha"] != self.state["candidate_sha"]:
            raise RuntimeError("human decision candidate identity mismatch")

        human = dict(pending)
        human["decision"] = decision
        human["decided_by"] = decided_by
        self.state["pending_decision"] = None
        self.write_json("human-decision.json", human)
        self.write_json(
            f"human-decision-{selected['id'].lower()}-attempt-{pending['attempt']:02d}.json",
            human,
        )
        self.event("human-decision-recorded", {
            "item": selected["id"],
            "attempt": pending["attempt"],
            "decision": decision,
            "decided_by": decided_by,
        })

        if decision == "reject":
            self._discard_candidate_branch()
            self.state["goal_status"] = "BLOCKED"
            return self.finish(
                "BLOCKED_POLICY",
                phase="BLOCKED_POLICY",
                reason="human authority rejected candidate",
                goal_satisfied=False,
            )

        if decision == "request_changes":
            review = {
                "blocking_findings": [{
                    "kind": "human-request-changes",
                    "severity": "blocking",
                    "message": "human authority requested another bounded proposal",
                }]
            }
            self._write_feedback(
                selected,
                pending["attempt"],
                review,
                source="human-request-changes",
            )
            self._discard_candidate_branch()
            next_attempt = pending["attempt"] + 1
            self.state["status"] = "RUNNING"
            self.state["phase"] = "PLANNING"
            self.state["attempt"] = next_attempt
            self.save_state()
            terminal = self._run_selected_item(selected, start_attempt=next_attempt)
            if terminal is not None:
                return terminal
            return self._reconcile_loop()

        self.state["status"] = "RUNNING"
        self.state["phase"] = "MERGE_PENDING"
        self.save_state()
        effect = self._prepare_merge_effect(self.state["candidate_sha"])
        merge_sha = self._perform_merge_effect(effect)
        self._consume_merge_effect(effect, merge_sha, recovered_existing=False)
        terminal = self._postmerge_verify_and_record(selected)
        if terminal is not None:
            return terminal
        return self._reconcile_loop()

    def recover_merge(self) -> dict:
        effect = self.state.get("pending_effect")
        if not effect or effect.get("effect") != "merge":
            raise RuntimeError(
                f"run is not resumable from merge: phase={self.state.get('phase')} pending={effect}"
            )
        before = self._find_merge_effects(effect["request_hash"])
        if len(before) > 1:
            raise RuntimeError("duplicate merge effects already exist")
        merge_sha = before[0] if before else self._perform_merge_effect(effect)
        self.write_json("recovery.json", {
            "schema": 2,
            "process_resumed": True,
            "request_hash": effect["request_hash"],
            "effect_occurrences_before_resume": len(before),
            "observed_existing_effect": bool(before),
            "duplicate_effect_prevented": len(before) == 1,
            "merge_sha": merge_sha,
        })
        self.event("run-resumed", {
            "request_hash": effect["request_hash"],
            "observed_existing_effect": bool(before),
        })
        self._consume_merge_effect(effect, merge_sha, recovered_existing=bool(before))
        selected = self._roadmap_item(self.state["current_item"])
        terminal = self._postmerge_verify_and_record(selected)
        if terminal is not None:
            return terminal
        return self._reconcile_loop()

    def build_summary(self, **extra) -> dict:
        seq, tip = EventLog.verify(self.evidence / "events.jsonl")
        summary = {
            "schema": 3,
            "reference_contract": REFERENCE_CONTRACT,
            "contracts": {
                "core": CORE_CONTRACT,
                "verification": VERIFICATION_PROFILE,
                "runtime": RUNTIME_PROFILE,
            },
            "run_id": self.run_id,
            "label": self.label,
            "status": self.state["status"],
            "phase": self.state["phase"],
            "goal_status": self.state["goal_status"],
            "event_count": seq,
            "event_tip": tip,
            "base_sha": self.state["base_sha"],
            "candidate_sha": self.state["candidate_sha"],
            "merge_sha": self.state["merge_sha"],
            "risk": self.state["risk"],
            "current_item": self.state["current_item"],
            "cycle": self.state["cycle"],
            "attempt": self.state["attempt"],
            "completed_items": list(self.state["completed_items"]),
            "evidence_directory": str(self.evidence),
            **extra,
        }
        self.write_json("run-summary.json", summary)
        return summary

    def finish(self, status: str, *, phase: str, **extra) -> dict:
        self.state["status"] = status
        self.state["phase"] = phase
        self.event("run-finished", {
            "status": status,
            "phase": phase,
            "goal_status": self.state.get("goal_status"),
        })
        self._write_control_loop()
        return self.build_summary(**extra)


def run_request(
    repository_root: Path,
    request: dict,
    output_root: Path,
    *,
    run_id: str | None = None,
) -> dict:
    return AutonomousEngine(
        repository_root,
        request,
        output_root,
        run_id=run_id,
    ).run()


def resume_run(
    repository_root: Path,
    run_dir: Path,
    *,
    decision: str | None = None,
    decided_by: str = "human",
) -> dict:
    engine = AutonomousEngine.resume_engine(repository_root, run_dir)
    if engine.authority_error:
        engine.state["goal_status"] = "BLOCKED"
        engine.event("policy-configuration-blocked", {"reason": engine.authority_error})
        return engine.finish(
            "BLOCKED_POLICY",
            phase="BLOCKED_POLICY",
            reason=f"policy configuration invalid during resume: {engine.authority_error}",
        )
    if engine.state.get("phase") == "AWAITING_DECISION":
        if decision is None:
            return engine.build_summary(goal_satisfied=False)
        return engine.apply_human_decision(decision, decided_by)
    if engine.state.get("pending_effect"):
        if decision is not None:
            raise RuntimeError("human decision supplied while recovering a merge effect")
        return engine.recover_merge()
    if engine.state.get("status") in TERMINAL_STATUSES:
        path = engine.evidence / "run-summary.json"
        return json.loads(path.read_text()) if path.is_file() else engine.build_summary()
    raise RuntimeError(
        f"run is not resumable: status={engine.state.get('status')} phase={engine.state.get('phase')}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Standalone bounded autonomous delivery reference runtime."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output", type=Path, default=Path(".demo/runs"))
    parser.add_argument("--scenario")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--decision", choices=["approve", "reject", "request_changes"])
    parser.add_argument("--decided-by", default="human")
    args = parser.parse_args(argv)

    try:
        if args.resume:
            summary = resume_run(
                args.repository_root.resolve(),
                args.resume.resolve(),
                decision=args.decision,
                decided_by=args.decided_by,
            )
        else:
            if not args.scenario:
                parser.error("--scenario is required unless --resume is used")
            goal = json.loads(
                (args.repository_root / "examples" / "goal.example.json").read_text()
            )
            request = build_request(
                args.repository_root.resolve(),
                args.scenario,
                goal,
            )
            summary = run_request(
                args.repository_root.resolve(),
                request,
                args.output.resolve(),
                run_id=args.run_id,
            )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except InjectedCrash as exc:
        print(str(exc), file=sys.stderr)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
