"""One read-only status projection for CLI, supervisor and embedded clients."""
from control_plane_core import recovery_actions
from .io import Closed


def status_document(state):
    if not isinstance(state, dict):
        raise Closed("Run state must be a JSON object")
    for name in ("task", "pending"):
        if state.get(name) is not None and not isinstance(state[name], dict):
            raise Closed("Invalid run state object: " + name)
    if (not isinstance(state.get("archive"), list)
            or any(not isinstance(row, dict) for row in state["archive"])
            or not isinstance(state.get("policy"), dict)
            or not isinstance(state["policy"].get("limits"), dict)):
        raise Closed("Invalid run state history or policy")
    task = state.get("task") or {}
    return {"run_id": state["run_id"], "status": state["status"],
            "phase": task.get("phase", state["phase"]), "paused": state["paused"],
            "revision": state.get("revision", 0), "updated_at": state.get("updated_at"),
            "item": task.get("id"), "head": task.get("head", state["base"]),
            "merge_sha": task.get("merge_sha", (state["archive"][-1].get("merge_sha") if state["archive"] else None)),
            "completed": state["completed"], "model_calls": state["model_calls"],
            "reason": state.get("reason"), "approval": task.get("approval_required"),
            "pending_effect": (state.get("pending") or {}).get("id"),
            "recovery": recovery_actions({**task, "agent_calls": state["model_calls"], "pending": state.get("pending")},
                {"max_agent_calls_per_task": state["policy"]["limits"]["model_calls"]}) if task else {}}
