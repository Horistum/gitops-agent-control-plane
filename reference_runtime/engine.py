from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from .recovery_engine import AutonomousEngine as _RecoveryAutonomousEngine, TERMINAL_STATUSES
from ._engine_impl import AutonomousEngine as _CoreAutonomousEngine
from .base import InjectedCrash, PolicyConfigurationError
from .contracts import load_json, matches_any, role_write_policy_ref, safe_relative_path
from .scenarios import build_request


class CandidateIdentityError(PolicyConfigurationError):
    pass


class AutonomousEngine(_RecoveryAutonomousEngine):
    """Public v7 engine with active role/authority config and exact Git identity binding."""

    @staticmethod
    def _role_for_actor(actor: str) -> str:
        return "test-designer" if actor == "tester" else actor

    def _role_write_patterns(self, actor: str) -> list[str]:
        role = self._role_for_actor(actor)
        try:
            write_ref = role_write_policy_ref(self.role_protocols, role)
        except ValueError as exc:
            raise PolicyConfigurationError(f"role protocol invalid for {role}: {exc}") from exc
        if write_ref == "none":
            return []
        patterns = self.policy.get(write_ref)
        if not isinstance(patterns, list) or not patterns:
            raise PolicyConfigurationError(
                f"role {role} references missing/non-list policy write authority {write_ref!r}"
            )
        return patterns

    def _authority_paths_from_model(self) -> list[str]:
        paths = list(self.policy["authority_paths"])
        for name in self.authority_model.get("artifacts", {}):
            paths.append(f".agent-control/{name}")
        return sorted(set(paths))

    def check_proposal(self, proposal: list[dict], *, actor: str) -> tuple[bool, list[dict]]:
        allowed_patterns = self._role_write_patterns(actor)
        forbidden = self.enforced_forbidden_patterns()
        authority_patterns = self._authority_paths_from_model()
        decisions: list[dict] = []
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
            in_allowed = bool(valid and allowed_patterns and matches_any(canonical, allowed_patterns))
            in_authority = bool(valid and matches_any(canonical, authority_patterns))
            is_forbidden = bool(valid and matches_any(canonical, forbidden))
            accepted = valid and in_allowed and not in_authority and not is_forbidden
            decisions.append({
                "actor": actor,
                "role_protocol": self._role_for_actor(actor),
                "path": raw,
                "canonical_path": canonical,
                "path_valid": valid,
                "path_error": error,
                "allowed_path": in_allowed,
                "authority_path": in_authority,
                "forbidden_path": is_forbidden,
                "accepted": accepted,
            })
            accepted_all = accepted_all and accepted
        return accepted_all, decisions

    def authority_snapshot(self, label: str) -> dict:
        snapshot = super().authority_snapshot(label)
        declared = {
            f".agent-control/{name}"
            for name in self.authority_model.get("artifacts", {})
            if name != "verification-probes.json"
        }
        missing = sorted(path for path in declared if path not in snapshot["files"])
        if missing:
            raise PolicyConfigurationError(
                f"authority-model declares workspace authority not covered by snapshot: {missing}"
            )
        return snapshot

    def _assert_controller_mutation(self, artifact: str) -> None:
        row = self.authority_model.get("artifacts", {}).get(artifact)
        if not isinstance(row, dict):
            raise PolicyConfigurationError(f"controller mutation target is not declared authority: {artifact}")
        if row.get("enforcement") != "machine" or row.get("mutation") != "controller-after-verified-effect":
            raise PolicyConfigurationError(
                f"controller lacks declared mutation authority for {artifact}: {row}"
            )

    def _human_pause(self, selected: dict, attempt: int, risk: str, reasons: list[str]) -> dict:
        summary = super()._human_pause(selected, attempt, risk, reasons)
        pending = self.state.get("pending_decision")
        if isinstance(pending, dict):
            pending = dict(pending)
            pending["observed_candidate_sha"] = None
            pending["candidate_identity_matches"] = None
            self.state["pending_decision"] = pending
            self.write_json("human-decision.json", pending)
            self.write_json(
                f"human-decision-{selected['id'].lower()}-attempt-{attempt:02d}.json",
                pending,
            )
            self.save_state()
            summary = self.build_summary(
                risk_decision=load_json(self.evidence / "risk-decision.json"),
                goal_satisfied=False,
            )
        return summary

    def _candidate_evidence_sha(self, pending: dict) -> str | None:
        path = self.evidence / (
            f"candidate-evidence-{pending['item'].lower()}-attempt-{pending['attempt']:02d}.json"
        )
        if not path.is_file():
            return None
        value = load_json(path)
        sha = value.get("candidate_sha")
        return sha if isinstance(sha, str) else None

    def _observe_candidate_identity(self, pending: dict) -> tuple[str | None, bool]:
        branch = pending.get("candidate_branch")
        expected = pending.get("candidate_sha")
        observed = None
        if isinstance(branch, str) and branch:
            candidate = self.git("rev-parse", f"refs/heads/{branch}", check=False)
            if re.fullmatch(r"[0-9a-f]{40}", candidate or ""):
                observed = candidate
        evidence_sha = self._candidate_evidence_sha(pending)
        state_sha = self.state.get("candidate_sha")
        matched = bool(
            observed
            and isinstance(expected, str)
            and expected == observed == evidence_sha == state_sha
        )
        return observed, matched

    def _persist_human_identity_observation(self, pending: dict) -> dict:
        observed, matched = self._observe_candidate_identity(pending)
        updated = dict(pending)
        updated["observed_candidate_sha"] = observed
        updated["candidate_identity_matches"] = matched
        self.state["pending_decision"] = updated
        self.write_json("human-decision.json", updated)
        self.write_json(
            f"human-decision-{updated['item'].lower()}-attempt-{updated['attempt']:02d}.json",
            updated,
        )
        self.save_state()
        return updated

    def apply_human_decision(self, decision: str, decided_by: str) -> dict:
        pending = self.state.get("pending_decision")
        if self.state.get("phase") != "AWAITING_DECISION" or not isinstance(pending, dict):
            return super().apply_human_decision(decision, decided_by)
        pending = self._persist_human_identity_observation(pending)
        if decision == "approve" and pending["candidate_identity_matches"] is not True:
            human = dict(pending)
            human["decision"] = decision
            human["decided_by"] = decided_by
            self.state["pending_decision"] = None
            self.write_json("human-decision.json", human)
            self.write_json(
                f"human-decision-{human['item'].lower()}-attempt-{human['attempt']:02d}.json",
                human,
            )
            self.event("human-decision-recorded", {
                "item": human["item"],
                "attempt": human["attempt"],
                "decision": decision,
                "decided_by": decided_by,
                "candidate_identity_matches": False,
            })
            self.event("human-approval-identity-blocked", {
                "item": human["item"],
                "expected_candidate_sha": human["candidate_sha"],
                "observed_candidate_sha": human["observed_candidate_sha"],
                "candidate_branch": human["candidate_branch"],
            })
            self._set_current_cycle_attempt_result("BLOCKED_POLICY", create_if_missing=False)
            self.state["goal_status"] = "BLOCKED"
            self._discard_candidate_branch()
            return self.finish(
                "BLOCKED_POLICY",
                phase="BLOCKED_POLICY",
                reason="candidate moved after human decision was requested",
                approved_candidate_sha=human["candidate_sha"],
                observed_candidate_sha=human["observed_candidate_sha"],
                goal_satisfied=False,
            )
        try:
            return super().apply_human_decision(decision, decided_by)
        except CandidateIdentityError as exc:
            self._set_current_cycle_attempt_result("BLOCKED_POLICY", create_if_missing=False)
            self.state["goal_status"] = "BLOCKED"
            self._discard_candidate_branch()
            return self.finish(
                "BLOCKED_POLICY",
                phase="BLOCKED_POLICY",
                reason=str(exc),
                goal_satisfied=False,
            )

    def _prepare_control_state_effect(self, selected: dict, verified_merge_sha: str) -> dict:
        self._assert_controller_mutation("release-state.json")
        return super()._prepare_control_state_effect(selected, verified_merge_sha)

    def _perform_merge_effect(self, effect: dict) -> str:
        existing = self._find_merge_effects(effect["request_hash"])
        if len(existing) > 1:
            raise RuntimeError("duplicate merge effects detected")
        if existing:
            return existing[0]
        branch = effect.get("candidate_branch")
        observed_candidate = self.git("rev-parse", f"refs/heads/{branch}", check=False)
        observed_base = self.git("rev-parse", "main", check=False)
        if observed_candidate != effect.get("candidate_sha"):
            raise CandidateIdentityError(
                "candidate branch moved after exact candidate revision was verified"
            )
        if observed_base != effect.get("base_sha"):
            raise CandidateIdentityError(
                "main moved after exact candidate revision was verified"
            )
        message = (
            f"Reference merge for {self.state['current_item']}\n\n"
            f"Effect-Id: {effect['request_hash']}"
        )
        try:
            return self.effect_adapter.merge_exact(
                effect["base_sha"], effect["candidate_sha"], message
            )
        except Exception as exc:
            raise CandidateIdentityError(
                "exact merge compare-and-swap failed because Git identity changed or merge failed"
            ) from exc

    def _consume_merge_effect(
        self,
        effect: dict,
        merge_sha: str,
        *,
        recovered_existing: bool,
    ) -> None:
        first_parent = self.git("rev-parse", f"{merge_sha}^1", check=False)
        second_parent = self.git("rev-parse", f"{merge_sha}^2", check=False)
        if first_parent != effect.get("base_sha") or second_parent != effect.get("candidate_sha"):
            raise CandidateIdentityError(
                "merge commit parents do not match the exact reviewed base/candidate revisions"
            )

        # Call the core consumer directly so merge evidence is enriched before
        # the recovery layer's post-receipt fault injection point can fire.
        _CoreAutonomousEngine._consume_merge_effect(
            self,
            effect,
            merge_sha,
            recovered_existing=recovered_existing,
        )
        value = load_json(self.evidence / "merge-evidence.json")
        value.update({
            "base_sha": effect["base_sha"],
            "actual_first_parent_sha": first_parent,
            "actual_second_parent_sha": second_parent,
            "candidate_identity_matches": True,
        })
        self.write_json("merge-evidence.json", value)
        item = self.state.get("current_item")
        if item:
            self.write_json(f"merge-evidence-{item.lower()}.json", value)

        if self.request.get("fault_injection") == "after-merge-receipt-before-postmerge":
            self.write_json("fault-injection.json", {
                "schema": 1,
                "point": self.request["fault_injection"],
                "effect_sha": merge_sha,
            })
            raise InjectedCrash(
                f"injected crash after merge receipt {merge_sha} before post-merge verification"
            )


def run_request(
    repository_root: Path,
    request: dict,
    output_root: Path,
    *,
    run_id: str | None = None,
) -> dict:
    return AutonomousEngine(repository_root, request, output_root, run_id=run_id).run()


def _block_identity_failure(engine: AutonomousEngine, exc: CandidateIdentityError) -> dict:
    engine.state["goal_status"] = "BLOCKED"
    engine._discard_candidate_branch()
    return engine.finish(
        "BLOCKED_POLICY",
        phase="BLOCKED_POLICY",
        reason=str(exc),
        goal_satisfied=False,
    )


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
        try:
            if effect.get("effect") == "merge":
                return engine.recover_merge()
            if effect.get("effect") == "control-state":
                return engine.recover_control_state()
        except CandidateIdentityError as exc:
            return _block_identity_failure(engine, exc)
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
            request = build_request(args.repository_root.resolve(), args.scenario, goal)
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
