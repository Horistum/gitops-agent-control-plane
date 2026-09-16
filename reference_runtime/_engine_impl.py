"""Internal composition for selection and reconciliation; public entry is engine.py."""
from __future__ import annotations

import json
from pathlib import Path

from control_plane_core import goal_projection

from .adapters import LocalGitEffectAdapter, LocalVerificationAdapter
from .attempts import CandidateAttemptMixin
from .base import BaseEngine, PolicyConfigurationError
from .contracts import (
    RUNTIME_PROFILE, load_json, validate_authority_model, validate_contract_set,
    validate_goal_against_roadmap, validate_release_state, validate_roadmap,
    validate_role_protocols,
)
from .human_decisions import HumanDecisionMixin
from .lifecycle_effects import LifecycleEffectsMixin
from .runtime_evidence import RuntimeEvidenceMixin

TERMINAL_STATUSES = {"COMPLETED", "BLOCKED_POLICY", "FAILED_VERIFICATION"}


class AutonomousEngine(
    CandidateAttemptMixin, HumanDecisionMixin, LifecycleEffectsMixin,
    RuntimeEvidenceMixin, BaseEngine,
):
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

    def load_authority(self) -> dict:
        value = super().load_authority()
        try:
            validate_roadmap(value["roadmap"])
            validate_release_state(value["release_state"], value["roadmap"])
            validate_goal_against_roadmap(self.goal, value["roadmap"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyConfigurationError(f"autonomous authority invalid: {exc}") from exc
        return value

    def _install_v7_runtime(self) -> None:
        self.contract_set: dict = {}
        self.role_protocols: dict = {"roles": {}}
        self.authority_model: dict = {}
        try:
            self.contract_set = load_json(self.repo / "config" / "contract-set.json")
            validate_contract_set(self.contract_set)
            self.role_protocols = load_json(self.repo / "config" / "role-protocols.json")
            validate_role_protocols(self.role_protocols)
            self.authority_model = load_json(self.workspace / ".agent-control" / "authority-model.json")
            validate_authority_model(self.authority_model)
        except (KeyError, TypeError, ValueError) as exc:
            if not self.authority_error:
                self.authority_error = f"autonomous control-plane configuration invalid: {exc}"

        raw_executor = self.executor
        self.verification_adapter = LocalVerificationAdapter(raw_executor)
        self.executor = self.verification_adapter
        self.effect_adapter = LocalGitEffectAdapter(self.git)
        if self.verification_adapter.profile != RUNTIME_PROFILE or self.effect_adapter.profile != RUNTIME_PROFILE:
            if not self.authority_error:
                self.authority_error = "runtime adapter profile mismatch"

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
        if self.contract_set:
            self.write_json("contract-set.json", self.contract_set)
        self._write_control_loop()

    @classmethod
    def resume_engine(cls, repository_root: Path, run_dir: Path) -> "AutonomousEngine":
        base = BaseEngine.resume_from(repository_root, run_dir)
        engine = cls.__new__(cls)
        engine.__dict__.update(base.__dict__)
        engine._install_v7_runtime()
        # BaseEngine.resume_from resolves authority using BaseEngine's method.
        # Re-read it through the v7 override so resume has the same semantic gate.
        if not engine.authority_error:
            try:
                engine.authority = engine.load_authority()
            except PolicyConfigurationError as exc:
                engine.authority = {}
                engine.authority_error = str(exc)
        return engine

    def eligible_items(self) -> list[dict]:
        projection = self._core_goal_projection()
        return [item for item in self.authority["roadmap"]["items"]
                if item["id"] in projection["eligible_items"]]

    def _core_goal_projection(self) -> dict:
        return goal_projection(
            self.goal["items"], self.authority["release_state"].get("completed", []),
            [{"id": item["id"], "dependencies": item.get("dependencies", []),
              "ready": item.get("status") == "ready"}
             for item in self.authority["roadmap"]["items"]])

    def _roadmap_item(self, item_id: str) -> dict:
        item = next((x for x in self.authority["roadmap"]["items"] if x["id"] == item_id), None)
        if item is None:
            raise PolicyConfigurationError(f"roadmap item missing during resume: {item_id}")
        return item

    def _goal_evaluation(self) -> dict:
        projection = self._core_goal_projection()
        value = {
            "schema": 1,
            "objective": self.goal["objective"],
            **{key: value for key, value in projection.items() if key != "unavailable_items"},
            "cycle": self.state["cycle"],
            "success_condition_semantics": "reasoning_context",
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


def run_request(repository_root, request, output_root, *, run_id=None):
    from .engine import run_request as public_run
    return public_run(repository_root, request, output_root, run_id=run_id)


def resume_run(repository_root, run_dir, *, decision=None, decided_by="human"):
    from .engine import resume_run as public_resume
    return public_resume(repository_root, run_dir, decision=decision, decided_by=decided_by)


def main(argv=None):
    from .engine import main as public_main
    return public_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
