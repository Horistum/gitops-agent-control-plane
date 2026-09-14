from __future__ import annotations

import argparse
import json
from pathlib import Path

from .base import BaseEngine
from .contracts import digest_tree, load_json, matches_any, risk_rank, sha256_bytes, sha256_json
from .scenarios import SUPPORTED, proposal_for


class DemoEngine(BaseEngine):
    def run(self) -> dict:
        self.write_json("goal.json", self.goal)
        self.write_json("policy.json", self.policy)
        self.state["status"] = "DISCOVERY"
        self.event("run-started", {"scenario": self.scenario})

        base_sha = self.init_git()
        self.state["base_sha"] = base_sha
        baseline = self.run_tests("baseline")
        if not baseline["passed"]:
            return self.finish("FAILED_VERIFICATION", reason="baseline failed")

        authority = self.authority_snapshot()
        roadmap = load_json(self.workspace / ".agent-control" / "roadmap.json")
        selected = next((x for x in roadmap["items"] if x["id"] in self.goal["items"] and x["status"] == "ready"), None)
        if not selected:
            return self.finish("BLOCKED_POLICY", reason="no authorized ready item")
        self.role_artifact("discovery", "accept", f"Selected {selected['id']}.", item=selected["id"])
        self.event("item-selected", {"item": selected["id"]})

        plan = {
            "schema": 1,
            "item": selected["id"],
            "objective": selected["goal"],
            "acceptance": selected["acceptance"],
            "working_set": ["src/reference_app/**", "tests/**"],
            "non_goals": selected["non_goals"],
            "verification": ["baseline tests", "candidate tests", "independent review", "post-merge tests"],
        }
        self.write_json("plan.json", plan)
        self.role_artifact("architect", "accept", "Bounded implementation plan created.", working_set=plan["working_set"])
        self.event("plan-created", {"plan_sha256": sha256_json(plan)})

        proposal = proposal_for(self.scenario)
        diff = self.diff_for(proposal)
        (self.evidence / "candidate.patch").write_text(diff)
        self.write_json(
            "proposal.json",
            {
                "schema": 1,
                "role": "developer",
                "edits": [{"path": e["path"], "reason": e["reason"], "content_sha256": sha256_bytes(e["content"].encode())} for e in proposal],
                "patch_sha256": sha256_bytes(diff.encode()),
            },
        )
        self.role_artifact("developer", "propose", "Produced a bounded candidate proposal.", changed_paths=[e["path"] for e in proposal])

        allowed, decisions = self.check_proposal(proposal)
        if not allowed:
            self.role_artifact(
                "reviewer",
                "block",
                "Proposal attempted to modify owner-controlled authority or a path outside the write envelope.",
                policy_decisions=decisions,
            )
            self.event("proposal-blocked", {"decisions": decisions})
            return self.finish("BLOCKED_POLICY", unauthorized_paths=[d["path"] for d in decisions if not d["accepted"]])

        self.git("checkout", "-b", "reference-candidate")
        self.apply_proposal(proposal)
        changed = [e["path"] for e in proposal]
        if len(changed) > self.policy["max_changed_files"] or len(diff.encode()) > self.policy["max_patch_bytes"]:
            self.event("proposal-blocked", {"reason": "change budget exceeded"})
            return self.finish("BLOCKED_POLICY", reason="change budget exceeded")

        risk = self.candidate_risk(changed)
        self.state["risk"] = risk
        if risk_rank(risk) > risk_rank(self.goal["risk_ceiling"]):
            self.event("risk-ceiling-exceeded", {"risk": risk, "ceiling": self.goal["risk_ceiling"]})
            return self.finish("BLOCKED_POLICY", reason="goal risk ceiling exceeded")

        self.git("add", ".")
        self.git("commit", "-m", f"Candidate for {selected['id']}")
        candidate_sha = self.git("rev-parse", "HEAD")
        self.state["candidate_sha"] = candidate_sha
        self.write_json(
            "candidate-evidence.json",
            {
                "schema": 1,
                "base_sha": base_sha,
                "candidate_sha": candidate_sha,
                "changed_paths": changed,
                "patch_sha256": sha256_bytes(diff.encode()),
                "tree_digest": digest_tree(self.workspace),
                "authority_snapshot_digest": authority["digest"],
            },
        )
        self.event("candidate-created", {"candidate_sha": candidate_sha, "changed_paths": changed})

        candidate_tests = self.run_tests("candidate")
        self.role_artifact(
            "tester",
            "accept" if candidate_tests["passed"] else "block",
            "Executed independent acceptance/regression tests.",
            test_evidence="test-candidate.json",
            tests=candidate_tests["tests"],
        )
        if not candidate_tests["passed"]:
            self.role_artifact("reviewer", "block", "Candidate verification failed; merge is forbidden.")
            self.event("candidate-verification-failed", {"candidate_sha": candidate_sha})
            return self.finish("FAILED_VERIFICATION", candidate_tests=candidate_tests)

        review = {
            "schema": 1,
            "role": "reviewer",
            "verdict": "accept",
            "candidate_sha": candidate_sha,
            "changed_paths": changed,
            "checks": {
                "acceptance_covered": True,
                "authority_unchanged": self.authority_snapshot()["digest"] == authority["digest"],
                "deterministic_tests_green": True,
                "scope_bounded": True,
            },
            "blocking_findings": [],
        }
        self.write_json("review.json", review)
        self.role_artifact("reviewer", "accept", "Candidate satisfies the bounded plan and executable evidence.", candidate_sha=candidate_sha)
        self.event("review-accepted", {"candidate_sha": candidate_sha})

        human_gate = risk_rank(risk) >= risk_rank(self.policy["human_gate_at"])
        auto_ceiling = self.goal["auto_merge_ceiling"]
        auto_allowed = auto_ceiling != "none" and risk_rank(risk) <= risk_rank(auto_ceiling)
        risk_decision = {
            "schema": 1,
            "risk": risk,
            "human_gate_required": human_gate,
            "auto_merge_ceiling": auto_ceiling,
            "auto_merge_allowed": auto_allowed and not human_gate,
            "critical_paths": [p for p in changed if matches_any(p, self.policy["critical_paths"])],
        }
        self.write_json("risk-decision.json", risk_decision)

        if human_gate or not auto_allowed:
            self.write_json(
                "human-decision.json",
                {
                    "schema": 1,
                    "required": True,
                    "reason": "risk/critical-path authority exceeds automatic merge boundary",
                    "candidate_sha": candidate_sha,
                    "risk": risk,
                    "decision": None,
                },
            )
            self.event("human-decision-required", {"candidate_sha": candidate_sha, "risk": risk})
            return self.finish("NEEDS_DECISION", risk_decision=risk_decision)

        if self.scenario == "crash-recovery":
            merge_sha = self.simulate_recovery_then_merge(candidate_sha)
        else:
            merge_sha = self.perform_merge(candidate_sha)

        postmerge = self.run_tests("postmerge")
        self.write_json(
            "postmerge-evidence.json",
            {
                "schema": 1,
                "merge_sha": merge_sha,
                "test_evidence": "test-postmerge.json",
                "passed": postmerge["passed"],
                "tests": postmerge["tests"],
            },
        )
        if not postmerge["passed"]:
            self.event("postmerge-verification-failed", {"merge_sha": merge_sha})
            return self.finish("FAILED_VERIFICATION", reason="post-merge verification failed")

        self.event("postmerge-verified", {"merge_sha": merge_sha, "tests": postmerge["tests"]})
        return self.finish(
            "COMPLETED",
            baseline_tests=baseline["tests"],
            candidate_tests=candidate_tests["tests"],
            postmerge_tests=postmerge["tests"],
            changed_paths=changed,
        )


def run_one(repository_root: Path, scenario: str, output_root: Path) -> dict:
    engine = DemoEngine(repository_root, scenario, output_root)
    return engine.run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone bounded-autonomy reference runtime.")
    parser.add_argument("--scenario", choices=SUPPORTED, default="happy-path")
    parser.add_argument("--output", type=Path, default=Path(".demo/runs"))
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    summary = run_one(args.repository_root, args.scenario, args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
