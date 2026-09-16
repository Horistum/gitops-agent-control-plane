"""Owner commands with exact bindings and quiescent upgrade/retirement gates."""
from __future__ import annotations

from control_plane_core import fingerprint, recovery_actions, require_merge_identity, retirement, upgrade_boundary
from .controller import Controller
from .io import Closed, locked
from .store import Store, runtime_fingerprint


def close_unmerged(engine):
    task = engine.task
    if task.get("merge_sha"):
        return {"merged": task["merge_sha"]}
    if task.get("pr"):
        number = task["pr"]["number"]
        def close(_):
            pull = engine.github.pull(number)
            engine.github.identity(pull, task["base"], task["head"])
            if pull.get("merged_at"):
                return {"merged": pull["merge_commit_sha"]}
            if pull.get("state") == "open":
                engine.github.api(engine.github.prefix + f"/pulls/{number}", "PATCH", {"state": "closed"})
            # Confirm the write; a concurrent merge must not be called cancellation.
            observed = engine.github.pull(number)
            engine.github.identity(observed, task["base"], task["head"])
            if observed.get("merged_at"):
                return {"merged": observed["merge_commit_sha"]}
            if observed.get("state") != "closed":
                raise Closed("PR closure did not establish an unmerged terminal state")
            return {"closed": number}
        return engine.store.effect("close-pr", {"number": number, "head": task["head"]}, close)
    return {}


def retire_attempt(engine):
    """Resume the persisted owner intent, including uncertain PR closure."""
    state, task = engine.state, engine.task
    name = state["owner_intent"]
    if task:
        result = close_unmerged(engine)
        if result.get("merged"):
            task["merge_sha"] = result["merged"]
            engine.store.save()
            if engine.github:
                engine.repo.fetch_merge(task["merge_sha"])
            require_merge_identity(task["base"], task["head"], engine.repo.parents(task["merge_sha"]))
            task["phase"] = "postmerge"
            state.update(status="RUNNING", phase="postmerge", stop_after_merge=name == "cancel")
            state.pop("owner_intent")
            return
        result = retirement(task, task["attempt"], state["archive"], name, status="cancelled")
        state["archive"].append(result["previous"])
        state["attempts"][task["id"]] = result["next_attempt"]
        if task.get("frozen_tests"):
            state.setdefault("carried_tests", {})[task["id"]] = task["frozen_tests"]
        state.setdefault("carried_risks", {})[task["id"]] = task["risk"]
        if name == "replan":
            count = state.setdefault("owner_replans", {}).get(task["id"], 0)
            state["owner_replans"][task["id"]] = count + 1
    state.update(task=None, discovery=None, status="CANCELLED" if name == "cancel" else "RUNNING", phase="reconcile")
    state["effect_epoch"] += 1
    state.pop("owner_intent")


def action(root, name, binding=None):
    root = root.resolve()
    with locked(root):
        engine = Controller(root)
        state, task = engine.state, engine.task
        if name == "pause":
            state["paused"] = True
        elif name == "continue":
            state["paused"] = False
        elif name == "approve":
            if (not task or not task.get("approvable") or state["status"] != "NEEDS_DECISION"
                    or binding != task.get("approval_required") or not binding):
                raise Closed("Approval must name the exact current candidate binding")
            task["approval"] = binding
            task["phase"] = task["resume_phase"]
            state["status"] = "RUNNING"
        elif name == "retry":
            permitted = recovery_actions({**(task or {}), "pending": state.get("pending"),
                "agent_calls": state["model_calls"]}, {"max_agent_calls_per_task": engine.policy["limits"]["model_calls"]})
            if not task or not permitted["retry"]:
                raise Closed("This hold is not retryable")
            task["phase"] = task["resume_phase"]
            state["status"] = "RUNNING"
            state["effect_epoch"] += 1
        elif name == "reconcile":
            pending = state.get("pending")
            if not pending or pending["kind"] == "model":
                raise Closed("No replay-safe pending effect to reconcile")
            if task and task["phase"] == "await_human":
                task["phase"] = task["resume_phase"]
            state["status"] = "RUNNING"
        elif name == "retry-effect":
            pending = state.get("pending")
            if not pending or pending["kind"] != "model" or pending["id"] != binding:
                raise Closed("Only an explicitly named indeterminate model call may be retried")
            if (root / "receipts" / (binding + ".json")).exists():
                raise Closed("A recorded model result must be reconciled, not repeated")
            state.setdefault("abandoned_effects", []).append(pending)
            state["pending"] = None
            state["effect_epoch"] += 1
            state["status"] = "RUNNING"
            if task and task["phase"] == "await_human":
                task["phase"] = task["resume_phase"]
        elif name in {"replan", "cancel"}:
            if state.get("owner_intent") not in {None, name}:
                raise Closed("Reconcile the existing owner intent first")
            if state.get("pending") and not (state.get("owner_intent") == name
                    and state["pending"]["kind"] == "close-pr"):
                raise Closed("Reconcile pending effects before retiring an attempt")
            if task and name == "replan" and state.get("owner_replans", {}).get(task["id"], 0) >= 2:
                raise Closed("Owner replan budget exhausted")
            state["owner_intent"] = name
            engine.store.save()
            retire_attempt(engine)
        else:
            raise Closed("Unknown owner action")
        engine.store.save()
        return engine.summary()


def upgrade(root, *, suspend=False):
    with locked(root):
        store = Store(root)
        state, task = store.state, store.state.get("task")
        if state.get("pending") or state.get("owner_intent"):
            raise Closed("Upgrade cannot cross a pending effect or owner intent")
        view = {"paused": state["paused"], "active": task["id"] if task else None,
                "tasks": {task["id"]: task} if task else {}, "active_goal": state["goal"]["id"],
                "goals": {state["goal"]["id"]: {"status": "active", "hash": fingerprint(state["goal"])}}}
        boundary = upgrade_boundary(view, suspend=suspend)
        if boundary["suspend"]:
            result = retirement(task, task["attempt"], state["archive"], "runtime-upgrade")
            state["archive"].append(result["previous"])
            state["attempts"][task["id"]] = result["next_attempt"]
            state.update(task=None, discovery=None, phase="reconcile", status="RUNNING")
        state["runtime_hash"] = runtime_fingerprint()
        state["effect_epoch"] += 1
        state["discovery"] = None
        store.save()
        return {"upgraded": True, "paused": True, "runtime_hash": state["runtime_hash"]}
