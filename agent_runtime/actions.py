"""Owner commands with exact bindings and quiescent upgrade/retirement gates."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from control_plane_core import fingerprint, require_merge_identity, retirement, upgrade_boundary
from .controller import Controller
from .decisions import approval_binding, decision_document, work_binding
from .discovery import remember_discovery
from .io import Closed, locked
from .store import Store, runtime_fingerprint, validate_authority
from .observations import status_document
from .recovery import task_recovery


def close_unmerged(engine):
    task = engine.task
    if task.get("merge_sha"):
        return {"merged": task["merge_sha"]}
    if task.get("pr"):
        number = task["pr"]["number"]
        published_head = task["pr"]["head"]
        def close(_):
            pull = engine.github.pull(number)
            engine.github.identity(pull, pull.get("base", {}).get("sha"), published_head)
            if pull.get("merged_at"):
                if published_head != task["head"]:
                    raise Closed("An earlier published candidate merged during repair; diagnosis is required")
                return {"merged": pull["merge_commit_sha"]}
            if pull.get("state") == "open":
                engine.github.api(engine.github.prefix + f"/pulls/{number}", "PATCH", {"state": "closed"})
            # Confirm the write; a concurrent merge must not be called cancellation.
            observed = engine.github.pull(number)
            engine.github.identity(observed, observed.get("base", {}).get("sha"), published_head)
            if observed.get("merged_at"):
                if published_head != task["head"]:
                    raise Closed("An earlier published candidate merged during repair; diagnosis is required")
                return {"merged": observed["merge_commit_sha"]}
            if observed.get("state") != "closed":
                raise Closed("PR closure did not establish an unmerged terminal state")
            return {"closed": number}
        return engine.store.effect("close-pr", {"number": number, "head": published_head}, close)
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
    if not task and name == "replan":
        remember_discovery(state)
    state.update(task=None, discovery=None, status="CANCELLED" if name == "cancel" else "RUNNING", phase="reconcile")
    state.pop("reason", None)
    state.pop("diagnostic", None)
    state["effect_epoch"] += 1
    state.pop("owner_intent")


def action(root, name, binding=None, *, decision_hash=None, reason=""):
    root = root.resolve()
    with locked(root):
        # Pause is a stop-only owner action. Do not instantiate a controller
        # whose changed executable identity prevents reaching the upgrade gate.
        engine = None if name == "pause" else Controller(root)
        store = Store(root) if engine is None else engine.store
        state, task = store.state, store.state.get("task")
        validate_authority(state)
        document = decision_document(state)
        if decision_hash is not None and decision_hash != document["decision_hash"]:
            raise Closed("Displayed decision changed; reload before acting")
        if not isinstance(reason, str) or len(reason) > 1000:
            raise Closed("Owner reason must be a bounded string")
        before = status_document(state)
        if ((state.get("technical_recovery") or {}).get("exhausted")
                and name not in {"continue", "pause", "cancel"}):
            raise Closed("Technical retry budget exhausted; continue the exact episode before another recovery action")
        if name == "pause":
            state["paused"] = True
        elif name == "continue":
            from .recovery import reset_technical_recovery
            reset_technical_recovery(state)
            state["paused"] = False
        elif name in {"approve", "approve-work"}:
            document = decision_document(state)
            work = name == "approve-work"
            purpose = "work-plan" if work else "candidate-merge"
            required = "work_approval_required" if work else "approval_required"
            current = work_binding(state) if work and task else approval_binding(state) if task else None
            if (not task or not task.get("approvable") or state["status"] != "NEEDS_DECISION"
                    or task.get("approval_purpose") != purpose
                    or not work and task.get("resume_phase") != "merge"
                    or binding != task.get(required) or not binding
                    or not document["approvable"] or binding != current):
                raise Closed("Approval must name the exact current " + ("work-plan" if work else "candidate") + " binding and purpose")
            if decision_hash is not None and decision_hash != document["decision_hash"]:
                raise Closed("Displayed decision changed; reload before approving")
            task["work_approval" if work else "approval"] = binding
            task["phase"] = task["resume_phase"]
            state["status"] = "RUNNING"
        elif name == "retry":
            permitted = task_recovery(state)
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
        elif name == "reconcile-effect":
            engine.reconcile_model(binding)
        elif name == "retry-effect":
            pending = state.get("pending")
            if (not pending or pending["kind"] != "model" or pending["id"] != binding
                    or pending.get("dispatch_state") == "not_started"):
                raise Closed("Only an explicitly named indeterminate model call may be retried")
            engine.store.recover_model_receipt(binding, getattr(engine.reasoning, "recover_completed", None))
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
            if not task and name == "replan" and state["model_calls"] >= engine.policy["limits"]["model_calls"]:
                raise Closed("Model call budget exhausted; discovery replan cannot reset it", code="MODEL_BUDGET_EXHAUSTED")
            state["owner_intent"] = name
            engine.store.save()
            retire_attempt(engine)
        else:
            raise Closed("Unknown owner action")
        if name in {"approve", "approve-work", "retry", "reconcile", "reconcile-effect", "retry-effect"}:
            state.pop("reason", None)
            state.pop("diagnostic", None)
        state.setdefault("human_actions", []).append({"action": name, "binding": binding,
            "decision_hash": document["decision_hash"], "authority": "local-owner",
            "action_id": uuid.uuid4().hex, "at": datetime.now(timezone.utc).isoformat(),
            "reason": reason, "before": {key: before[key] for key in ("status", "phase", "head")},
            "after": {key: status_document(state)[key] for key in ("status", "phase", "head")}})
        store.save()
        return status_document(state)


def upgrade(root, *, suspend=False):
    with locked(root):
        store = Store(root)
        state, task = store.state, store.state.get("task")
        validate_authority(state)
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
        if not task:
            remember_discovery(state)
        state["runtime_hash"] = runtime_fingerprint()
        state["effect_epoch"] += 1
        state["discovery"] = None
        store.save()
        return {"upgraded": True, "paused": True, "runtime_hash": state["runtime_hash"]}
