"""Normalize operational recovery inputs once for projections and owner actions."""
from control_plane_core import recovery_actions


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
