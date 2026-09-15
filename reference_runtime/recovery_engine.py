from __future__ import annotations

from control_plane_core import completion_transition, require_revision_identity

import argparse
import json
from pathlib import Path
import sys

from ._engine_impl import AutonomousEngine as _CoreAutonomousEngine, TERMINAL_STATUSES
from .base import InjectedCrash
from .contracts import load_json, sha256_json
from .scenarios import build_request


class AutonomousEngine(_CoreAutonomousEngine):
    """Public v7 engine facade with durable effect and phase recovery."""

    def _set_current_cycle_attempt_result(self, result: str, *, create_if_missing: bool) -> None:
        item = self.state.get("current_item")
        cycle = self.state.get("cycle", 0)
        attempt = self.state.get("attempt", 0)
        if not item or cycle < 1 or attempt < 1:
            return
        value = self._control_loop_value()
        row = next(
            (
                candidate
                for candidate in value.get("cycles", [])
                if candidate.get("cycle") == cycle and candidate.get("item") == item
            ),
            None,
        )
        if row is None:
            if not create_if_missing:
                return
            attempts: list[dict] = []
            for prior in range(1, attempt):
                feedback = self.evidence / f"feedback-{item.lower()}-attempt-{prior:02d}.json"
                if feedback.is_file():
                    attempts.append({"attempt": prior, "result": "REPAIR_REQUESTED"})
            attempts.append({"attempt": attempt, "result": result})
            value.setdefault("cycles", []).append({
                "cycle": cycle,
                "item": item,
                "attempts": attempts,
                "result": result,
            })
        else:
            attempts = row.setdefault("attempts", [])
            attempt_row = next((candidate for candidate in attempts if candidate.get("attempt") == attempt), None)
            if attempt_row is None:
                attempts.append({"attempt": attempt, "result": result})
            else:
                attempt_row["result"] = result
            row["result"] = result
        value["completed_items"] = list(self.state.get("completed_items", []))
        value["goal_satisfied"] = self.state.get("goal_status") == "SATISFIED"
        self.write_json("control-loop.json", value)

    def apply_human_decision(self, decision: str, decided_by: str) -> dict:
        if decision == "request_changes":
            self._set_current_cycle_attempt_result("REPAIR_REQUESTED", create_if_missing=False)
        elif decision == "reject":
            self._set_current_cycle_attempt_result("BLOCKED_POLICY", create_if_missing=False)
        return super().apply_human_decision(decision, decided_by)

    def _consume_merge_effect(
        self,
        effect: dict,
        merge_sha: str,
        *,
        recovered_existing: bool,
    ) -> None:
        super()._consume_merge_effect(
            effect,
            merge_sha,
            recovered_existing=recovered_existing,
        )
        if self.request.get("fault_injection") == "after-merge-receipt-before-postmerge":
            self.write_json("fault-injection.json", {
                "schema": 1,
                "point": self.request["fault_injection"],
                "effect_sha": merge_sha,
            })
            raise InjectedCrash(
                f"injected crash after merge receipt {merge_sha} before post-merge verification"
            )

    def _desired_release_state(self, selected: dict, verified_merge_sha: str) -> dict:
        release_path = self.workspace / ".agent-control" / "release-state.json"
        release = load_json(release_path)
        completed = list(release.get("completed", []))
        history = [dict(row) for row in release.get("history", [])]
        item_id = selected["id"]
        verified = load_json(self.evidence / f"postmerge-evidence-{item_id.lower()}.json")
        require_revision_identity({"merge_sha": verified_merge_sha, "tested_sha": verified_merge_sha}, verified)
        transition = completion_transition(self.goal["items"], completed, item_id,
                                           merge_sha=verified_merge_sha,
                                           verification_passed=verified.get("passed"))
        if item_id not in completed:
            completed = transition["completed"]
            history.append({
                "item": item_id,
                "verified_merge_sha": verified_merge_sha,
                "recorded_by": "controller",
            })
        else:
            rows = [row for row in history if row.get("item") == item_id]
            if len(rows) != 1 or rows[0].get("verified_merge_sha") != verified_merge_sha:
                raise RuntimeError("existing release-state item does not match verified merge identity")
        return {
            "schema": release["schema"],
            "completed": completed,
            "history": history,
            "notes": list(release.get("notes", [])),
        }

    def _prepare_control_state_effect(self, selected: dict, verified_merge_sha: str) -> dict:
        desired = self._desired_release_state(selected, verified_merge_sha)
        desired_digest = sha256_json(desired)
        control_state_id = sha256_json({
            "item": selected["id"],
            "verified_merge_sha": verified_merge_sha,
            "desired_release_state_sha256": desired_digest,
        })
        request = {
            "effect": "control-state",
            "item": selected["id"],
            "verified_merge_sha": verified_merge_sha,
            "base_sha": self.git("rev-parse", "main"),
            "desired_release_state_sha256": desired_digest,
            "control_state_id": control_state_id,
        }
        effect = {
            **request,
            "desired_release_state": desired,
            "request_hash": sha256_json(request),
        }
        self.state["pending_effect"] = effect
        self.state["phase"] = "CONTROL_STATE_PENDING"
        self.state["status"] = "WAITING_EXTERNAL"
        intent = {"schema": 1, **effect}
        self.write_json("control-state-intent.json", intent)
        self.write_json(f"control-state-intent-{selected['id'].lower()}.json", intent)
        self.event("effect-intent-persisted", {
            "kind": "control-state",
            "request_hash": effect["request_hash"],
            "control_state_id": control_state_id,
            "item": selected["id"],
        })
        return effect

    def _find_control_state_effects(self, control_state_id: str) -> list[str]:
        return self.effect_adapter.find_trailer_effect("Control-State-Id", control_state_id)

    def _perform_control_state_effect(self, effect: dict) -> str:
        desired = effect.get("desired_release_state")
        if not isinstance(desired, dict) or sha256_json(desired) != effect["desired_release_state_sha256"]:
            raise RuntimeError("durable control-state intent payload digest mismatch")
        existing = self._find_control_state_effects(effect["control_state_id"])
        if len(existing) > 1:
            raise RuntimeError("duplicate control-state effects detected")
        if existing:
            return existing[0]
        self.git("checkout", "main")
        release_path = self.workspace / ".agent-control" / "release-state.json"
        release_path.write_text(json.dumps(desired, indent=2, sort_keys=True) + "\n")
        message = (
            f"Record verified completion of {effect['item']}\n\n"
            f"Control-State-Id: {effect['control_state_id']}"
        )
        return self.effect_adapter.commit_control_state(
            [".agent-control/release-state.json"],
            message,
        )

    def _consume_control_state_effect(
        self,
        effect: dict,
        control_state_sha: str,
        *,
        recovered_existing: bool,
    ) -> None:
        commits = self._find_control_state_effects(effect["control_state_id"])
        if commits != [control_state_sha]:
            raise RuntimeError(
                f"control-state effect identity mismatch: {commits} expected {[control_state_sha]}"
            )
        self.git("checkout", "main")
        release_path = self.workspace / ".agent-control" / "release-state.json"
        observed = load_json(release_path)
        if sha256_json(observed) != effect["desired_release_state_sha256"]:
            raise RuntimeError("control-state commit content does not match durable intent")
        transition = {
            "schema": 1,
            "item": effect["item"],
            "verified_merge_sha": effect["verified_merge_sha"],
            "control_state_id": effect["control_state_id"],
            "release_state_sha": control_state_sha,
        }
        self.write_json(f"release-transition-{effect['item'].lower()}.json", transition)
        self.state["pending_effect"] = None
        self.state["status"] = "RUNNING"
        self.state["phase"] = "RECONCILE"
        self.state["base_sha"] = control_state_sha
        self.authority = self.load_authority()
        self.state["completed_items"] = list(self.authority["release_state"]["completed"])
        self._set_current_cycle_attempt_result("COMPLETED", create_if_missing=False)
        self.event("effect-consumed", {
            "kind": "control-state",
            "request_hash": effect["request_hash"],
            "control_state_id": effect["control_state_id"],
            "control_state_sha": control_state_sha,
            "recovered_existing_effect": recovered_existing,
        })
        self.event("release-state-transition", {
            "item": effect["item"],
            "verified_merge_sha": effect["verified_merge_sha"],
            "release_state_sha": control_state_sha,
            "control_state_id": effect["control_state_id"],
        })
        if self.request.get("fault_injection") == "after-release-state-receipt-before-reconcile":
            self.write_json("fault-injection.json", {
                "schema": 1,
                "point": self.request["fault_injection"],
                "effect_sha": control_state_sha,
            })
            raise InjectedCrash(
                f"injected crash after control-state receipt {control_state_sha} before reconciliation"
            )

    def _record_release_state(self, selected: dict, verified_merge_sha: str) -> str:
        effect = self._prepare_control_state_effect(selected, verified_merge_sha)
        control_state_sha = self._perform_control_state_effect(effect)
        if self.request.get("fault_injection") == "after-release-state-effect-before-receipt":
            self.write_json("fault-injection.json", {
                "schema": 1,
                "point": self.request["fault_injection"],
                "effect_sha": control_state_sha,
            })
            raise InjectedCrash(
                f"injected crash after control-state effect {control_state_sha} before receipt"
            )
        self._consume_control_state_effect(
            effect,
            control_state_sha,
            recovered_existing=False,
        )
        return control_state_sha

    def _write_phase_recovery(self, from_phase: str, action: str) -> None:
        artifact = {
            "schema": 1,
            "process_resumed": True,
            "from_phase": from_phase,
            "action": action,
            "item": self.state.get("current_item"),
            "candidate_sha": self.state.get("candidate_sha"),
            "merge_sha": self.state.get("merge_sha"),
            "completed_items": list(self.state.get("completed_items", [])),
        }
        self.write_json("phase-recovery.json", artifact)
        self.event("phase-recovery", artifact)

    def recover_control_state(self) -> dict:
        effect = self.state.get("pending_effect")
        if not effect or effect.get("effect") != "control-state":
            raise RuntimeError(
                f"run is not resumable from control-state effect: phase={self.state.get('phase')} pending={effect}"
            )
        if sha256_json(effect.get("desired_release_state")) != effect.get("desired_release_state_sha256"):
            raise RuntimeError("persisted control-state intent payload digest mismatch")
        before = self._find_control_state_effects(effect["control_state_id"])
        if len(before) > 1:
            raise RuntimeError("duplicate control-state effects already exist")
        control_state_sha = before[0] if before else self._perform_control_state_effect(effect)
        recovery = {
            "schema": 1,
            "process_resumed": True,
            "effect": "control-state",
            "request_hash": effect["request_hash"],
            "control_state_id": effect["control_state_id"],
            "effect_occurrences_before_resume": len(before),
            "observed_existing_effect": bool(before),
            "duplicate_effect_prevented": len(before) == 1,
            "control_state_sha": control_state_sha,
        }
        self.write_json("control-state-recovery.json", recovery)
        self.event("run-resumed", {
            "effect": "control-state",
            "request_hash": effect["request_hash"],
            "observed_existing_effect": bool(before),
        })
        self._consume_control_state_effect(
            effect,
            control_state_sha,
            recovered_existing=bool(before),
        )
        self._set_current_cycle_attempt_result("COMPLETED", create_if_missing=True)
        return self._reconcile_loop()

    def recover_phase(self) -> dict:
        phase = self.state.get("phase")
        if self.state.get("pending_effect") is not None:
            raise RuntimeError("phase recovery cannot run while a durable effect is pending")
        if self.state.get("status") != "RUNNING":
            raise RuntimeError(f"phase recovery requires RUNNING state, observed {self.state.get('status')}")

        if phase == "POSTMERGE_VERIFY":
            item = self.state.get("current_item")
            if not item or not self.state.get("merge_sha"):
                raise RuntimeError("POSTMERGE_VERIFY recovery lacks item/merge identity")
            self._write_phase_recovery(phase, "rerun-postmerge-verification")
            selected = self._roadmap_item(item)
            terminal = self._postmerge_verify_and_record(selected)
            if terminal is not None:
                return terminal
            self._set_current_cycle_attempt_result("COMPLETED", create_if_missing=True)
            return self._reconcile_loop()

        if phase == "RECONCILE":
            item = self.state.get("current_item")
            self._write_phase_recovery(phase, "continue-goal-reconciliation")
            if item and item in set(self.authority["release_state"].get("completed", [])):
                self._set_current_cycle_attempt_result("COMPLETED", create_if_missing=True)
            return self._reconcile_loop()

        raise RuntimeError(f"phase is not safely resumable without a pending effect: {phase}")


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
            goal_satisfied=False,
        )
    if engine.state.get("phase") == "AWAITING_DECISION":
        if decision is None:
            return engine.build_summary(goal_satisfied=False)
        return engine.apply_human_decision(decision, decided_by)
    effect = engine.state.get("pending_effect")
    if isinstance(effect, dict):
        if decision is not None:
            raise RuntimeError("human decision supplied while recovering a durable effect")
        if effect.get("effect") == "merge":
            return engine.recover_merge()
        if effect.get("effect") == "control-state":
            return engine.recover_control_state()
        raise RuntimeError(f"unsupported pending effect during resume: {effect.get('effect')}")
    if engine.state.get("status") in TERMINAL_STATUSES:
        path = engine.evidence / "run-summary.json"
        return json.loads(path.read_text()) if path.is_file() else engine.build_summary()
    if engine.state.get("phase") in {"POSTMERGE_VERIFY", "RECONCILE"}:
        if decision is not None:
            raise RuntimeError("human decision supplied during phase recovery")
        return engine.recover_phase()
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
            goal = load_json(args.repository_root / "examples" / "goal.example.json")
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
