"""Purpose-bound approval identities and one decision projection for CLI and web."""
from __future__ import annotations

import copy
from control_plane_core import fingerprint
from .recovery import reset_technical_recovery, task_recovery
from .io import Closed
from .discovery import can_replan_discovery, discovery_document
from .diagnostics import current_diagnostic
from .authorization import approval_binding, work_binding, work_critical_paths
from .reverification import recovery_binding


def technical_continue_allowed(state):
    """Project the same exact episode check that the owner command executes."""
    try:
        return reset_technical_recovery(copy.deepcopy(state))
    except Closed:
        return False


def owner_actions(state, diagnostic=None):
    task, pending = state.get("task") or {}, state.get("pending")
    if (diagnostic or {}).get("code") == "AUTHORITY_CHANGED":
        return []
    if (diagnostic or {}).get("code") == "RUNTIME_CHANGED":
        return [] if state["paused"] else ["pause"]
    allowed = ["continue" if state["paused"] else "pause"]
    if technical_continue_allowed(state) and "continue" not in allowed:
        allowed.append("continue")
    if pending:
        if not (pending["kind"] == "model" and pending.get("dispatch_state") == "not_started"):
            allowed.extend(["reconcile-effect", "retry-effect"] if pending["kind"] == "model" else ["reconcile"])
        return allowed
    allowed.append("cancel")
    if (state.get("technical_recovery") or {}).get("exhausted"):
        return allowed
    if (task and state.get("owner_replans", {}).get(task["id"], 0) < 2) or can_replan_discovery(state):
        allowed.append("replan")
    if recovery_binding(state):
        allowed.append("reverify")
    return allowed


def decision_document(state):
    task = state.get("task") or {}
    frame = task or state.get("discovery") or {}
    item = next((row for row in state["goal"]["items"] if row["id"] == task.get("id")), None)
    purpose = task.get("approval_purpose")
    work = purpose == "work-plan"
    binding = (work_binding(state) if work else approval_binding(state)) if task else None
    required = task.get("work_approval_required" if work else "approval_required")
    merge_hold = purpose == "candidate-merge" and task.get("resume_phase") == "merge"
    diagnostic = current_diagnostic(state)
    drift = (diagnostic or {}).get("code") in {"RUNTIME_CHANGED", "AUTHORITY_CHANGED"}
    document = {"schema": 1, "run_id": state["run_id"], "status": state["status"],
        "paused": state["paused"], "phase": task.get("phase", state["phase"]),
        "reason": state.get("reason"), "item": item, "attempt": task.get("attempt"),
        "head": task.get("head"), "base": task.get("base"), "risk": task.get("risk"),
        "spec_hash": task.get("spec_hash"), "policy_hash": state["policy_hash"],
        "runtime_hash": state["runtime_hash"], "binding": binding, "approval_purpose": purpose,
        "approval_action": "approve-work" if work else "approve",
        "work_plan": {"steps": task.get("plan", []), "scenarios": task.get("test_design", []),
                      "working_files": task.get("working_set", []),
                      "critical_paths": work_critical_paths(state) if task else []},
        "approvable": bool(task.get("approvable") and state["status"] == "NEEDS_DECISION"
            and (work or merge_hold) and required == binding and not state.get("pending")
            and not state.get("owner_intent") and not drift),
        "diagnostic": diagnostic,
        "technical_recovery": state.get("technical_recovery"),
        "reverification_binding": recovery_binding(state),
        "verification_recovery": task.get("verification_recovery"),
        "technical_continue_allowed": not drift and technical_continue_allowed(state),
        "reviews": frame.get("role_results", {}), "feedback": frame.get("feedback", []),
        "discovery": discovery_document(state),
        "previous_discovery": state.get("discovery_retry"),
        "evidence": {key: task[key] for key in ("candidate_evidence", "independent_baseline",
            "independent_evidence", "candidate_obligations", "integration_obligations",
            "obligations", "acceptance", "ci_evidence", "integration_evidence") if key in task},
        "pull_request": task.get("pr")}
    document["actions"] = owner_actions(state, diagnostic)
    document["pending_effect"] = (state.get("pending") or {}).get("id")
    document["recent_actions"] = state.get("human_actions", [])[-30:]
    document["decision_hash"] = fingerprint(document)
    return copy.deepcopy(document)
