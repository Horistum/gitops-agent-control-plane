"""One exact approval identity and one decision projection for CLI and web."""
from __future__ import annotations

import copy
from control_plane_core import fingerprint, recovery_actions
from .discovery import can_replan_discovery, discovery_document


def owner_actions(state):
    task, pending = state.get("task") or {}, state.get("pending")
    allowed = ["continue" if state["paused"] else "pause"]
    if pending:
        allowed.extend(["reconcile-effect", "retry-effect"] if pending["kind"] == "model" else ["reconcile"])
        return allowed
    allowed.append("cancel")
    if (task and state.get("owner_replans", {}).get(task["id"], 0) < 2) or can_replan_discovery(state):
        allowed.append("replan")
    if recovery_actions({**task, "pending": pending, "agent_calls": state["model_calls"]},
            {"max_agent_calls_per_task": state["policy"]["limits"]["model_calls"]})["retry"]:
        allowed.append("retry")
    return allowed


def approval_binding(state):
    task = state["task"]
    return fingerprint({"base": task["base"], "head": task["head"], "spec_hash": task["spec_hash"],
        "risk": task["risk"], "policy_hash": state["policy_hash"],
        "runtime_hash": state["runtime_hash"], "run_id": state["run_id"]})


def decision_document(state):
    task = state.get("task") or {}
    frame = task or state.get("discovery") or {}
    item = next((row for row in state["goal"]["items"] if row["id"] == task.get("id")), None)
    binding = approval_binding(state) if task else None
    document = {"schema": 1, "run_id": state["run_id"], "status": state["status"],
        "paused": state["paused"], "phase": task.get("phase", state["phase"]),
        "reason": state.get("reason"), "item": item, "attempt": task.get("attempt"),
        "head": task.get("head"), "base": task.get("base"), "risk": task.get("risk"),
        "spec_hash": task.get("spec_hash"), "policy_hash": state["policy_hash"],
        "runtime_hash": state["runtime_hash"], "binding": binding,
        "approvable": bool(task.get("approvable") and state["status"] == "NEEDS_DECISION"
            and task.get("approval_required") == binding and not state.get("pending")
            and not state.get("owner_intent")),
        "reviews": frame.get("role_results", {}), "feedback": frame.get("feedback", []),
        "discovery": discovery_document(state),
        "previous_discovery": state.get("discovery_retry"),
        "evidence": {key: task[key] for key in ("candidate_evidence", "independent_baseline",
            "independent_evidence", "candidate_obligations", "integration_obligations",
            "obligations", "acceptance", "ci_evidence", "integration_evidence") if key in task},
        "pull_request": task.get("pr")}
    document["actions"] = owner_actions(state)
    document["pending_effect"] = (state.get("pending") or {}).get("id")
    document["recent_actions"] = state.get("human_actions", [])[-30:]
    document["decision_hash"] = fingerprint(document)
    return copy.deepcopy(document)
