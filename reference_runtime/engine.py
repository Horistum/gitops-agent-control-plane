from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .base import BaseEngine, InjectedCrash
from .contracts import load_json, risk_rank, sha256_bytes, sha256_json
from .scenarios import build_request


def _role(engine: BaseEngine, role: str, verdict: str, summary: str, **extra) -> None:
    engine.write_json(f"role-{role}.json", {"schema": 2, "role": role, "verdict": verdict, "summary": summary, **extra})


class ReferenceEngine(BaseEngine):
    def run(self) -> dict:
        self.transition("BASELINE_VERIFY")
        base_sha = self.init_git()
        self.state["base_sha"] = base_sha
        self.save_state()
        baseline = self.run_tests("baseline")
        if not baseline["passed"] or baseline["tests"] < self.policy["minimum_baseline_tests"]:
            return self.finish("FAILED_VERIFICATION", phase="FAILED_VERIFICATION", reason="baseline verification failed")

        authority_before = self.authority_snapshot("baseline")
        protected_before = self.protected_test_snapshot("baseline")

        self.transition("DISCOVERY")
        roadmap = self.authority["roadmap"]
        release = self.authority["release_state"]
        completed = set(release.get("completed", []))
        selected = next((item for item in roadmap["items"] if item["id"] in self.goal["items"] and item["status"] == "ready" and set(item.get("dependencies", [])) <= completed), None)
        if not selected:
            return self.finish("BLOCKED_POLICY", phase="BLOCKED_POLICY", reason="no authorized ready item")
        _role(self, "discovery", "accept", f"Selected {selected['id']}.", item=selected["id"])
        self.event("item-selected", {"item": selected["id"]})

        self.transition("PLANNING")
        plan = {
            "schema": 2,
            "item": selected["id"],
            "objective": selected["goal"],
            "acceptance": selected["acceptance"],
            "developer_working_set": self.policy["developer_allowed_paths"],
            "tester_working_set": self.policy["tester_allowed_paths"],
            "non_goals": selected["non_goals"],
            "verification": ["protected baseline tests", "required acceptance test identities", "exact candidate SHA test binding", "computed review", "post-merge exact SHA verification"],
        }
        self.write_json("plan.json", plan)
        _role(self, "architect", "accept", "Bounded plan created from structured authority.", plan_sha256=sha256_json(plan))
        self.event("plan-created", {"plan_sha256": sha256_json(plan)})

        developer = self.request["developer_proposal"]
        tester = self.request["tester_proposal"]
        _role(self, "developer", "propose", "Developer proposed implementation edits.", changed_paths=[x["path"] for x in developer])
        _role(self, "test-designer", "propose", "Independent tester proposed acceptance-test edits.", changed_paths=[x["path"] for x in tester])

        self.transition("PROPOSAL_GATES")
        dev_ok, dev_decisions = self.check_proposal(developer, actor="developer")
        tester_ok, tester_decisions = self.check_proposal(tester, actor="tester")
        decisions = dev_decisions + tester_decisions
        self.write_json("policy-decision.json", {"schema": 2, "accepted": dev_ok and tester_ok, "files": decisions})
        if not dev_ok or not tester_ok:
            self.event("proposal-blocked", {"decisions": decisions})
            return self.finish("BLOCKED_POLICY", phase="BLOCKED_POLICY", unauthorized_paths=[row["path"] for row in decisions if not row["accepted"]])

        developer_diff = self.diff_for(developer)
        tester_diff = self.diff_for(tester)
        combined_diff = developer_diff + tester_diff
        changed = [row["canonical_path"] for row in decisions]
        self.write_json("proposal.json", {
            "schema": 2,
            "developer_edits": [{"path": x["path"], "content_sha256": sha256_bytes(x["content"].encode())} for x in developer],
            "tester_edits": [{"path": x["path"], "content_sha256": sha256_bytes(x["content"].encode())} for x in tester],
            "patch_sha256": sha256_bytes(combined_diff.encode()),
        })
        (self.evidence / "candidate.patch").write_text(combined_diff)

        if len(changed) > self.policy["max_changed_files"] or len(combined_diff.encode()) > self.policy["max_patch_bytes"]:
            self.event("budget-blocked", {"changed_files": len(changed), "max_changed_files": self.policy["max_changed_files"], "patch_bytes": len(combined_diff.encode()), "max_patch_bytes": self.policy["max_patch_bytes"]})
            return self.finish("BLOCKED_POLICY", phase="BLOCKED_POLICY", reason="change budget exceeded before write")

        risk, risk_matches = self.candidate_risk(changed)
        self.state["risk"] = risk
        self.save_state()
        if risk_rank(risk) > risk_rank(self.goal["risk_ceiling"]):
            self.event("risk-ceiling-exceeded", {"risk": risk, "ceiling": self.goal["risk_ceiling"], "matches": risk_matches})
            return self.finish("BLOCKED_POLICY", phase="BLOCKED_POLICY", reason="goal risk ceiling exceeded before write")

        self.transition("CANDIDATE_APPLY")
        self.git("checkout", "-b", "reference-candidate")
        self.apply_proposal(developer)
        self.apply_proposal(tester)
        authority_candidate = self.authority_snapshot("candidate")
        protected_candidate = self.protected_test_snapshot("candidate")
        if authority_candidate["digest"] != authority_before["digest"]:
            self.rollback_uncommitted_candidate()
            self.event("authority-drift-blocked", {"before": authority_before["digest"], "after": authority_candidate["digest"]})
            return self.finish("BLOCKED_POLICY", phase="BLOCKED_POLICY", reason="authority changed during candidate application")
        if protected_candidate["digest"] != protected_before["digest"]:
            self.rollback_uncommitted_candidate()
            self.event("protected-tests-drift-blocked", {"before": protected_before["digest"], "after": protected_candidate["digest"]})
            return self.finish("BLOCKED_POLICY", phase="BLOCKED_POLICY", reason="protected baseline tests changed")

        self.transition("CANDIDATE_COMMIT")
        self.git("add", ".")
        self.git("commit", "-m", f"Candidate for {selected['id']}")
        candidate_sha = self.git("rev-parse", "HEAD")
        self.state["candidate_sha"] = candidate_sha
        self.save_state()
        from .contracts import digest_tree
        self.write_json("candidate-evidence.json", {
            "schema": 2, "base_sha": base_sha, "candidate_sha": candidate_sha, "changed_paths": changed,
            "patch_sha256": sha256_bytes(combined_diff.encode()), "tree_digest": digest_tree(self.workspace),
            "authority_snapshot_before": authority_before["digest"], "authority_snapshot_candidate": authority_candidate["digest"],
            "protected_tests_before": protected_before["digest"], "protected_tests_candidate": protected_candidate["digest"],
        })
        self.event("candidate-created", {"candidate_sha": candidate_sha, "changed_paths": changed})

        self.transition("CANDIDATE_VERIFY")
        candidate_tests = self.run_tests("candidate")
        _role(self, "tester", "accept" if candidate_tests["passed"] else "block", "Executed protected baseline and independent acceptance tests.", tested_sha=candidate_tests["tested_sha"], tests=candidate_tests["tests"])
        if not candidate_tests["passed"]:
            self.event("candidate-verification-failed", {"candidate_sha": candidate_sha})
            return self.finish("FAILED_VERIFICATION", phase="FAILED_VERIFICATION", reason="candidate tests failed")

        self.transition("REVIEW")
        review = self.compute_review(selected=selected, changed_paths=changed, policy_decisions=decisions, authority_before=authority_before, authority_after=authority_candidate, protected_before=protected_before, protected_after=protected_candidate, baseline=baseline, candidate_tests=candidate_tests, candidate_sha=candidate_sha)
        self.write_json("review.json", review)
        _role(self, "reviewer", review["verdict"], "Computed candidate review from execution evidence.", checks=review["checks"], blocking_findings=review["blocking_findings"])
        if review["verdict"] != "accept":
            self.event("review-blocked", {"candidate_sha": candidate_sha, "findings": review["blocking_findings"]})
            return self.finish("FAILED_VERIFICATION", phase="FAILED_VERIFICATION", reason="computed review blocked candidate")

        self.event("review-accepted", {"candidate_sha": candidate_sha})
        self.transition("RISK_GATE")
        human_gate = risk_rank(risk) >= risk_rank(self.policy["human_gate_at"])
        auto_ceiling = self.goal["auto_merge_ceiling"]
        auto_allowed = auto_ceiling != "none" and risk_rank(risk) <= risk_rank(auto_ceiling)
        risk_decision = {
            "schema": 2, "risk": risk, "matched_rules": risk_matches, "human_gate_required": human_gate,
            "auto_merge_ceiling": auto_ceiling, "auto_merge_allowed": auto_allowed and not human_gate,
            "decision_reasons": (["HUMAN_GATE_THRESHOLD"] if human_gate else []) + (["AUTO_MERGE_CEILING"] if not auto_allowed else []),
        }
        self.write_json("risk-decision.json", risk_decision)
        if human_gate or not auto_allowed:
            self.write_json("human-decision.json", {"schema": 2, "required": True, "candidate_sha": candidate_sha, "risk": risk, "reasons": risk_decision["decision_reasons"], "decision": None})
            self.event("human-decision-required", {"candidate_sha": candidate_sha, "risk": risk, "reasons": risk_decision["decision_reasons"]})
            return self.finish("NEEDS_DECISION", phase="AWAITING_DECISION", risk_decision=risk_decision)

        effect = self.prepare_merge_effect(candidate_sha)
        merge_sha = self.perform_merge_effect(effect)
        if self.request.get("fault_injection") == "after-merge-effect-before-receipt":
            self.write_json("fault-injection.json", {"schema": 1, "point": self.request["fault_injection"], "effect_sha": merge_sha})
            raise InjectedCrash(f"injected crash after merge effect {merge_sha} before receipt")
        self.consume_merge_effect(effect, merge_sha, recovered_existing=False)
        return self._postmerge_and_finish(baseline, selected)

    def _postmerge_and_finish(self, baseline: dict, selected: dict) -> dict:
        self.transition("POSTMERGE_VERIFY")
        merge_sha = self.state["merge_sha"]
        postmerge = self.run_tests("postmerge")
        required = self.acceptance_test_identities(selected)
        observed = set(postmerge["test_identities"])
        passed = postmerge["passed"] and postmerge["tested_sha"] == merge_sha and set(baseline["test_identities"]) <= observed and required <= observed and postmerge["tests"] >= self.policy["minimum_candidate_tests"]
        self.write_json("postmerge-evidence.json", {"schema": 2, "merge_sha": merge_sha, "tested_sha": postmerge["tested_sha"], "passed": passed, "tests": postmerge["tests"], "baseline_identities_preserved": set(baseline["test_identities"]) <= observed, "acceptance_identities_present": required <= observed})
        if not passed:
            self.event("postmerge-verification-failed", {"merge_sha": merge_sha})
            return self.finish("FAILED_VERIFICATION", phase="FAILED_VERIFICATION", reason="post-merge verification failed")
        self.event("postmerge-verified", {"merge_sha": merge_sha, "tests": postmerge["tests"]})
        return self.finish("COMPLETED", phase="COMPLETED", baseline_tests=baseline["tests"], candidate_sha=self.state["candidate_sha"], merge_sha=merge_sha, postmerge_tests=postmerge["tests"])


def run_request(repository_root: Path, request: dict, output_root: Path, *, run_id: str | None = None) -> dict:
    return ReferenceEngine(repository_root, request, output_root, run_id=run_id).run()


def resume_run(repository_root: Path, run_dir: Path) -> dict:
    base = BaseEngine.resume_from(repository_root, run_dir)
    if base.state["status"] in {"COMPLETED", "BLOCKED_POLICY", "FAILED_VERIFICATION", "NEEDS_DECISION"}:
        return load_summary(base)
    effect = base.state.get("pending_effect")
    if not effect or effect.get("effect") != "merge":
        raise RuntimeError(f"run is not resumable: phase={base.state.get('phase')} pending={effect}")
    before = base.effect_merge_commits(effect["request_hash"])
    if len(before) > 1:
        raise RuntimeError("duplicate merge effects already exist")
    merge_sha = before[0] if before else base.perform_merge_effect(effect)
    base.write_json("recovery.json", {"schema": 2, "process_resumed": True, "request_hash": effect["request_hash"], "effect_occurrences_before_resume": len(before), "observed_existing_effect": bool(before), "duplicate_effect_prevented": len(before) == 1, "merge_sha": merge_sha})
    base.event("run-resumed", {"request_hash": effect["request_hash"], "observed_existing_effect": bool(before)})
    base.consume_merge_effect(effect, merge_sha, recovered_existing=bool(before))
    engine = ReferenceEngine.__new__(ReferenceEngine)
    engine.__dict__.update(base.__dict__)
    baseline = load_json(base.evidence / "test-baseline.json")
    selected = next(item for item in base.authority["roadmap"]["items"] if item["id"] in base.goal["items"])
    return engine._postmerge_and_finish(baseline, selected)


def load_summary(base: BaseEngine) -> dict:
    path = base.evidence / "run-summary.json"
    return json.loads(path.read_text()) if path.is_file() else base.build_summary()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone bounded-autonomy reference runtime.")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path(".demo/runs"))
    parser.add_argument("--scenario")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    try:
        if args.resume:
            summary = resume_run(args.repository_root.resolve(), args.resume.resolve())
        else:
            if not args.scenario:
                parser.error("--scenario is required unless --resume is used")
            base_goal = json.loads((args.repository_root / "examples" / "goal.example.json").read_text())
            request = build_request(args.repository_root.resolve(), args.scenario, base_goal)
            summary = run_request(args.repository_root.resolve(), request, args.output.resolve(), run_id=args.run_id)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except InjectedCrash as exc:
        print(json.dumps({"status": "CRASH_INJECTED", "error": str(exc)}, indent=2), file=sys.stderr)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
