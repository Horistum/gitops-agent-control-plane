from __future__ import annotations

from control_plane_core.execution import verification_transition
from .acceptance import evaluate as evaluate_acceptance


import json

from .contracts import sha256_json


class LifecycleEffectsMixin:
    """Internal controller responsibility; composed only by the public engine."""

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
        typed = evaluate_acceptance(self, selected, post_probes, "postmerge")
        passed = passed and typed["complete"]
        self.event("typed-acceptance-evaluated", typed)
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
        if verification_transition("postmerge", bool(passed)) != "done":
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
