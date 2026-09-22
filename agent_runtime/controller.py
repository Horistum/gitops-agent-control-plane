"""Bounded goal reconciliation using shared decisions and injected I/O adapters."""
from __future__ import annotations

import copy
from pathlib import Path
import uuid
from control_plane_core import (CoreError, context_checkpoint, context_files, context_view,
    evaluate_goal_conditions, fingerprint, goal_projection, recovery_actions,
    risk_rank)
from control_plane_core.schema import SchemaValidationError
from .context import requested_context, role_view
from .contracts import ROLE_SCHEMAS, criteria, validate_configuration, normalize_role_output
from .discovery import initial_discovery
from .git import GitRepository
from .github import GitHub
from .io import Closed, Unavailable, canonical, locked, read_json
from .reasoning import Reasoning
from .store import Store, runtime_fingerprint
from .verification import Verification


class Controller:
    def __init__(self, root, *, reasoning=None, verification=None, github=None):
        self.root = Path(root).resolve()
        self.store = Store(self.root)
        self.policy, self.goal = self.store.state["policy"], self.store.state["goal"]
        validate_configuration(self.policy, self.goal)
        if self.store.state["policy_hash"] != fingerprint({"policy": self.policy, "goal": self.goal}):
            raise Closed("Saved authority snapshot changed")
        if self.store.state["runtime_hash"] != runtime_fingerprint():
            raise Closed("Runtime changed; use the explicit quiescent upgrade command")
        self.repo = GitRepository(self.root / "product.git", self.policy["base_branch"])
        self.reasoning = reasoning or Reasoning(self.policy["reasoning"])
        self.verification = verification or Verification(self.policy["execution"])
        self.github = github or (GitHub(self.policy["publication"], self.policy["base_branch"])
                                 if self.policy["publication"]["kind"] == "github" else None)

    @classmethod
    def start(cls, root, policy, goal, *, trusted_local=False):
        root, product = Path(root).resolve(), Path(policy["product"]).resolve()
        validate_configuration(policy, goal)
        if root.is_relative_to(product) or product.is_relative_to(root):
            raise Closed("Run state and product checkout must be separate directories")
        if policy["execution"]["kind"] == "trusted-local" and not trusted_local:
            raise Closed("Local execution requires --trusted-local and owner-trusted product code")
        with locked(root):
            if (root / "state.json").exists():
                raise Closed("Existing run; use resume")
            Reasoning(policy["reasoning"]).preflight()
            Verification(policy["execution"]).preflight()
            if policy["publication"]["kind"] == "github":
                GitHub(policy["publication"], policy["base_branch"]).preflight()
            from .initialization import initialize
            repo, run_id = initialize(root, policy, goal)
            Store(root, {"schema": 1, "run_id": run_id, "policy": copy.deepcopy(policy),
                "goal": copy.deepcopy(goal), "policy_hash": fingerprint({"policy": policy, "goal": goal}),
                "runtime_hash": runtime_fingerprint(), "status": "RUNNING", "phase": "reconcile",
                "base": repo.resolve(policy["base_branch"]), "task": None, "discovery": None,
                "completed": [], "criteria": {}, "cli_cases": {}, "history": [], "archive": [],
                "attempts": {}, "model_calls": 0, "pending": None, "effect_epoch": 1, "paused": False}).save()
        return cls(root)

    @classmethod
    def resume(cls, root):
        root = Path(root).resolve()
        if not (root / "state.json").exists():
            intent = read_json(root / "initialization.json")
            return cls.start(root, intent["policy"], intent["goal"],
                             trusted_local=intent["policy"]["execution"]["kind"] == "trusted-local")
        return cls(root)

    @property
    def state(self):
        return self.store.state

    @property
    def task(self):
        return self.state["task"]

    def item(self):
        return next(item for item in self.goal["items"] if item["id"] == self.task["id"])

    def advance(self, phase=None):
        old = phase or self.task["phase"]
        from .workflow import transition
        transition(self, {"kind": "advance"}, old)

    def hold(self, reason, *, kind="FAILED", approvable=False):
        self.state.update(status="NEEDS_DECISION" if approvable else kind, reason=reason)
        if self.task:
            self.task.update(resume_phase=self.task["phase"], phase="await_human", hold_kind=kind,
                             approvable=approvable, retryable=kind == "FAILED")

    def reconcile_model(self, binding):
        """Restore only a held call's execution frame; the next tick consumes its receipt."""
        pending = self.state.get("pending")
        if not pending or pending.get("kind") != "model" or pending.get("id") != binding:
            raise Closed("Model reconciliation must name the exact pending effect")
        receipt = self.store.read_receipt(binding)
        request = pending["request"]
        task = self.task or {}
        expected = {"kind": "model", "policy_hash": self.state["policy_hash"],
                    "runtime_hash": self.state["runtime_hash"], "run_id": self.state["run_id"],
                    "epoch": self.state["effect_epoch"], "item": task.get("id"),
                    "attempt": task.get("attempt"), "turn": task.get("turn", 0)}
        if (receipt["request"] != request or fingerprint(request) != binding
                or any(request.get(key) != value for key, value in expected.items())):
            raise Closed("Pending model receipt authority or attempt differs")
        payload = request["payload"]
        phase = payload.get("phase")
        if phase not in ROLE_SCHEMAS or payload.get("goal") != self.goal:
            raise Closed("Pending model request phase or goal differs")
        holder = self.task if self.task is not None else self.state.get("discovery")
        if not isinstance(holder, dict) or not isinstance(payload.get("task"), dict):
            raise Closed("Pending model execution frame is missing")
        restored = copy.deepcopy(holder)
        # hold() changes only these fields. Never roll back source, memory,
        # acceptance, policy or other business data to make a receipt fit.
        if self.task and holder.get("phase") == "await_human":
            if holder.get("resume_phase") != phase:
                raise Closed("Held model phase differs from original request")
            for key in ("phase", "resume_phase", "hold_kind", "approvable", "retryable"):
                if key in payload["task"]:
                    restored[key] = copy.deepcopy(payload["task"][key])
                else:
                    restored.pop(key, None)
        if role_view(restored, phase) != payload["task"]:
            raise Closed("Model execution frame changed; cannot reuse old evidence")
        holder.clear()
        holder.update(restored)
        self.state.update(status="RUNNING", phase=phase if self.task else "reconcile")
        self.state.pop("reason", None)
        # Keep pending, epoch, turn and reservation. Normal dispatch validates
        # the whole reconstructed request before replay, without provider I/O.

    def model(self, phase, task, extra=None):
        limits = self.policy["limits"]
        if task.get("context_rounds", 0) >= limits["context_rounds"]:
            raise Closed("Context/protocol round budget exhausted")
        revision = fingerprint({key: task.get(key) for key in ("head", "base", "spec_hash", "goal_hash")} |
                               {"authority": self.state["policy_hash"]})
        memory = task.setdefault("memory", {})
        previous = context_view(memory, phase, revision)
        required = task.get("context", [])
        if phase in {"reviewer", "challenge_review", "architect_accept", "chief_accept"}:
            required = list(dict.fromkeys(required + self.repo.changed(task["base"], task["head"])))
        retained = list(previous.get("sources", {}))
        if phase == "discovery":
            # Seed selection from eligible items, but let explicit retrieval
            # replace seeds when the union is larger than the context window.
            retained = required + retained
            required = []
        paths, omitted = context_files(required, task.get("requested_files", []),
                                       retained, limits["context_files"])
        sources = self.repo.context(task["head"], paths, limits["context_bytes"])
        payload = {"phase": phase, "goal": self.goal, "task": role_view(task, phase),
                   "sources": sources, "omitted_paths": omitted, "memory": previous,
                   "authority": {key: self.policy[key] for key in ("allowed_paths", "test_paths", "protected_paths")},
                   "criteria": criteria(self.item()) if self.task else [], **(extra or {})}
        if len(canonical(payload)) > limits["context_bytes"] + 200_000:
            raise Closed("Complete model input exceeds prompt limit")
        try:
            result = self.store.effect("model", payload,
                lambda identity: self.reasoning.execute({**payload, "effect_id": identity}),
                prepare=getattr(self.reasoning, "prepare", None))
        finally:
            discard = getattr(self.reasoning, "discard_preparation", None)
            if discard:
                discard()
        task["turn"] = task.get("turn", 0) + 1
        if result.get("protocol_error"):
            task["context_rounds"] = task.get("context_rounds", 0) + 1
            task.setdefault("feedback", []).append({"kind": "protocol", "detail": result["protocol_error"]})
            return None
        output = normalize_role_output(result["result"])
        # Validate here too: alternative in-process adapters have no privileged bypass.
        from control_plane_core.schema import validate_instance
        validate_instance(output, ROLE_SCHEMAS[phase])
        if phase == "discovery":
            task["last_result"] = {key: output[key] for key in ("verdict", "summary", "selected_item")}
        memory[phase] = context_checkpoint(previous, revision=revision, phase=phase,
            summary=output["summary"], sources=sources, requests={key: output[key] for key in ("requested_files", "requested_searches", "requested_facts")},
            facts=task.get("external_facts", {}),
            turn_id=str(task["turn"]))
        if output["verdict"] == "need_context":
            if memory[phase]["repeats"] >= 2:
                raise Closed("Context request makes no progress")
            try:
                requested_context(self, task, output)
            except Closed as exc:
                task.setdefault("feedback", []).append({"kind": "context_protocol", "detail": str(exc)})
            task["context_rounds"] = task.get("context_rounds", 0) + 1
            return None
        task["requested_files"], task["context_rounds"] = [], 0
        task.setdefault("role_results", {})[phase] = {"summary": output["summary"], "head": task["head"],
                                                     "verdict": output["verdict"], "base": task["base"],
                "spec_hash": task.get("spec_hash"), "acceptance_evidence": output["acceptance_evidence"],
                "findings": output["findings"], "risk": output["risk"]}
        if phase == "discovery":
            task["role_results"][phase]["selected_item"] = output["selected_item"]
        return output

    def reconcile(self):
        projection = goal_projection([row["id"] for row in self.goal["items"]], self.state["completed"], self.goal["items"])
        self.state["projection"] = projection
        if projection["satisfied"]:
            result = evaluate_goal_conditions(self.goal["machine_conditions"], self.state)
            self.state["goal_evidence"] = result
            if not result["passed"]:
                raise Closed("Requested items completed, but machine goal conditions remain unsatisfied")
            self.state.update(status="COMPLETED", phase="done")
            return
        if not projection["eligible_items"]:
            raise Closed("No dependency-ready authorized item")
        if self.state["discovery"] is None:
            head = self.repo.remote_base() if self.github else self.repo.resolve(self.policy["base_branch"])
            if self.github:
                self.repo.text("update-ref", "refs/heads/" + self.policy["base_branch"], head)
            self.state["discovery"] = initial_discovery(self.state, head, projection["eligible_items"])
        discovery = self.state["discovery"]
        output = self.model("discovery", discovery, {"eligible_items": projection["eligible_items"]})
        if output is None:
            return
        if output["verdict"] != "ready" or output["selected_item"] not in projection["eligible_items"]:
            raise Closed("Discovery did not select eligible authorized work: "
                f"verdict={output['verdict']}, selected_item={output['selected_item']!r}, "
                f"eligible_items={projection['eligible_items']!r}. "
                f"Model summary: {output['summary']}")
        item = next(row for row in self.goal["items"] if row["id"] == output["selected_item"])
        attempt = self.state["attempts"].get(item["id"], 1)
        head = discovery["head"]
        self.state["task"] = {"id": item["id"], "goal_id": self.goal["id"], "goal_hash": fingerprint(self.goal),
            "phase": "baseline", "base": head, "head": head, "spec_hash": fingerprint(item),
            "risk": max((item["risk"], self.state.get("carried_risks", {}).get(item["id"], "low")), key=risk_rank), "context": item["context"], "attempt": attempt, "repairs": 0, "turn": 0,
            "feedback": [], "memory": {}, "role_results": {}, "working_set": [], "completed_phases": [],
            "frozen_tests": self.state.get("carried_tests", {}).get(item["id"])}
        self.state["discovery"] = None
        self.state.pop("discovery_retry", None)

    def tick(self):
        from .roles import role_step, apply_step
        from .lifecycle import lifecycle_step
        with locked(self.root):
            self.store.state = Store(self.root).state
            if (self.state["policy_hash"] != fingerprint({"policy": self.policy, "goal": self.goal})
                    or self.state["policy_hash"] != fingerprint({"policy": self.state["policy"], "goal": self.state["goal"]})):
                raise Closed("Authority changed during this run")
            if self.state["runtime_hash"] != runtime_fingerprint():
                raise Closed("Runtime changed during this run")
            if self.state["paused"] or (not self.state.get("owner_intent") and self.state["status"] in {"COMPLETED", "CANCELLED", "NEEDS_DECISION", "FAILED", "BLOCKED_POLICY"}):
                return self.summary()
            self.state["status"] = "RUNNING"
            self.state.pop("reason", None)
            phase = self.task["phase"] if self.task else "reconcile"
            try:
                if self.state.get("owner_intent"):
                    from .actions import retire_attempt
                    retire_attempt(self)
                elif self.task is None:
                    self.reconcile()
                elif phase in ROLE_SCHEMAS:
                    role_step(self)
                elif phase.startswith("apply_"):
                    apply_step(self)
                else:
                    lifecycle_step(self)
            except Unavailable as exc:
                self.state.update(status="WAITING_EXTERNAL", reason=str(exc))
            except (Closed, CoreError, SchemaValidationError, ValueError) as exc:
                self.hold(str(exc), kind="BLOCKED_POLICY")
            self.state["phase"] = self.task["phase"] if self.task else self.state.get("phase", "reconcile")
            self.state["history"].append({"phase": phase, "next": self.state["phase"], "status": self.state["status"]})
            self.store.save()
            return self.summary()

    def summary(self):
        from .observations import status_document
        return status_document(self.state)
