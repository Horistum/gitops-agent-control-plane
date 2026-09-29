"""One read-only status projection for CLI, supervisor and embedded clients."""
from .recovery import task_recovery
from .discovery import can_replan_discovery, discovery_document
from .io import Closed
from .diagnostics import current_diagnostic


def product_document(root, state):
    """Observe only the run-owned local ref; never fetch or touch the checkout."""
    from pathlib import Path
    from .git import GitRepository
    from .diagnostics import safe_text
    policy = state["policy"]
    repository = Path(root).resolve() / "product.git"
    ref = "refs/heads/" + policy["base_branch"]
    result = {"source_checkout": policy["product"], "repository": str(repository),
              "base_ref": ref, "base_ref_sha": None, "inspection_error": None,
              "publication": policy["publication"]["kind"],
              "note": "The source checkout is unchanged. This is the run-owned local ref, not a live remote observation."}
    try:
        result["base_ref_sha"] = GitRepository(repository, policy["base_branch"]).resolve(ref)
    except Exception as exc:
        result["inspection_error"] = safe_text(exc)
    return result


def status_document(state, root=None):
    if not isinstance(state, dict):
        raise Closed("Run state must be a JSON object")
    for name in ("task", "pending", "discovery"):
        if state.get(name) is not None and not isinstance(state[name], dict):
            raise Closed("Invalid run state object: " + name)
    if (not isinstance(state.get("archive"), list)
            or any(not isinstance(row, dict) for row in state["archive"])
            or not isinstance(state.get("policy"), dict)
            or not isinstance(state["policy"].get("limits"), dict)):
        raise Closed("Invalid run state history or policy")
    task = state.get("task") or {}
    discovery = discovery_document(state)
    result = {"run_id": state["run_id"], "status": state["status"],
            "phase": task.get("phase", state["phase"]), "paused": state["paused"],
            "revision": state.get("revision", 0), "updated_at": state.get("updated_at"),
            "item": task.get("id"), "head": task.get("head", (discovery or {}).get("head", state["base"])),
            "merge_sha": task.get("merge_sha", (state["archive"][-1].get("merge_sha") if state["archive"] else None)),
            "completed": state["completed"], "model_calls": state["model_calls"],
            "reason": state.get("reason"), "approval": task.get("work_approval_required"
                if task.get("approval_purpose") == "work-plan" else "approval_required"),
            "approval_purpose": task.get("approval_purpose"),
            "diagnostic": current_diagnostic(state),
            "technical_recovery": state.get("technical_recovery"),
            "pending_effect": (state.get("pending") or {}).get("id"),
            "discovery": discovery,
            "recovery": task_recovery(state) if task else
                {"retry": False, "replan": can_replan_discovery(state)}}
    if root is not None:
        result["product"] = product_document(root, state)
    return result
