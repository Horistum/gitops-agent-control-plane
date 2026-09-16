from __future__ import annotations


from .contracts import load_json


class HumanDecisionMixin:
    """Internal controller responsibility; composed only by the public engine."""

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
