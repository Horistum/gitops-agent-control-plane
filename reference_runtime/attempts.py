from __future__ import annotations

from control_plane_core.execution import repair_target
from .acceptance import evaluate as evaluate_acceptance

from control_plane_core import merge_authority

import json

from .base import InjectedCrash
from .contracts import digest_tree, load_json, sha256_bytes, sha256_json


class CandidateAttemptMixin:
    """Internal controller responsibility; composed only by the public engine."""

    def _write_feedback(self, selected: dict, attempt: int, review: dict, *, source: str) -> dict:
        feedback = {
            "schema": 1,
            "item": selected["id"],
            "attempt": attempt,
            "route": repair_target("reviewer", "fix", review.get("blocking_findings", [])) + "-repair",
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
        if merge_authority(risk, risk_ceiling=self.goal["risk_ceiling"],
                           auto_merge_ceiling=self.goal["auto_merge_ceiling"],
                           human_gate_at=self.policy["human_gate_at"])["blocked"]:
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
        typed = evaluate_acceptance(self, selected, probes, "candidate")
        review["checks"]["typed_acceptance"] = typed["passed"]
        if not typed["passed"]:
            review["verdict"] = "block"
            review["blocking_findings"].append({"kind": "evidence", "severity": "high", "message": "Due typed acceptance lacks evidence"})
        self.event("typed-acceptance-evaluated", typed)
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
        authority = merge_authority(risk, risk_ceiling=self.goal["risk_ceiling"],
                                    auto_merge_ceiling=self.goal["auto_merge_ceiling"],
                                    human_gate_at=self.policy["human_gate_at"])
        human_gate = authority["human_gate_required"]
        auto_ceiling = self.goal["auto_merge_ceiling"]
        auto_allowed = authority["auto_merge_allowed"]
        risk_decision = {
            "schema": 2,
            "risk": risk,
            "matched_rules": risk_matches,
            "human_gate_required": human_gate,
            "auto_merge_ceiling": auto_ceiling,
            "auto_merge_allowed": auto_allowed and not human_gate,
            "decision_reasons": authority["decision_reasons"],
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
