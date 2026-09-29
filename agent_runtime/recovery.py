"""Normalize operational recovery inputs once for projections and owner actions."""
from control_plane_core import CoreError, recovery_actions
from control_plane_core.execution import technical_recovery
from .io import Closed, NotDispatched


def technical_status(state, now):
    """Project persisted retry deadlines without resetting any work budget."""
    return technical_recovery(state.get("technical_recovery", {}), now=now)


def technical_failure(engine, exc, now):
    """A dispatched model without a receipt remains an explicit owner boundary."""
    state, pending = engine.state, engine.state.get("pending")
    if (pending and pending.get("kind") == "model"
            and pending.get("dispatch_state") != "not_started"
            and not (engine.root / "receipts" / (pending["id"] + ".json")).exists()):
        raise Closed("Indeterminate model call; explicit retry-effect must name " + pending["id"]
                     + "; provider failure: " + str(exc), code="MODEL_OUTCOME_UNKNOWN",
                     details=getattr(exc, "details", {})) from exc
    category = "not_dispatched" if isinstance(exc, NotDispatched) else "transport"
    previous = state.get("technical_recovery", {})
    decision = technical_recovery(previous, now=now, failure_kind=category,
                                  retry_after=getattr(exc, "retry_after", 0))
    state["technical_recovery"] = {**decision["checkpoint"],
        "policy_hash": state["policy_hash"], "runtime_hash": state["runtime_hash"],
        "pending_id": (pending or {}).get("id")}
    return decision


def reset_technical_recovery(state):
    """Explicit owner continuation may reset only an exhausted technical episode."""
    checkpoint = state.get("technical_recovery") or {}
    try:
        decision = technical_recovery(checkpoint, now=0)
    except CoreError as exc:
        raise Closed(str(exc)) from exc
    if decision["action"] != "exhausted":
        return False
    if (state.get("status") != "FAILED" or
            (state.get("diagnostic") or {}).get("code") != "TECHNICAL_RETRY_EXHAUSTED" or
            checkpoint.get("policy_hash") != state["policy_hash"] or
            checkpoint.get("runtime_hash") != state["runtime_hash"] or
            checkpoint.get("pending_id") != (state.get("pending") or {}).get("id")):
        raise Closed("Technical recovery reset does not match the current exhausted episode")
    task = state.get("task")
    if task:
        if task.get("phase") != "await_human" or task.get("hold_kind") != "FAILED":
            raise Closed("Technical recovery task changed before owner continuation")
        task["phase"] = task["resume_phase"]
        task["retryable"] = False
    state.setdefault("technical_recovery_history", []).append(dict(checkpoint))
    state.pop("technical_recovery")
    state.update(status="RUNNING")
    state.pop("reason", None)
    state.pop("diagnostic", None)
    return True


def task_recovery(state):
    """Do not mutate state or reset lifetime budgets while projecting recovery."""
    task = state.get("task") or {}
    policy_limits = state["policy"]["limits"]
    limits = {"max_agent_calls_per_task": policy_limits["model_calls"]}
    # Production policy requires this field. Preserve the core's legacy default
    # for minimal read-only projections instead of inventing a second default.
    if "context_rounds" in policy_limits:
        limits["max_context_rounds"] = policy_limits["context_rounds"]
    diagnostic = state.get("diagnostic") or {}
    view = {**task, "pending": state.get("pending"), "agent_calls": state["model_calls"],
            "owner_replans": state.get("owner_replans", {}).get(task.get("id"), 0),
            "failure_code": diagnostic.get("code", task.get("failure_code"))}
    return recovery_actions(view, limits)
