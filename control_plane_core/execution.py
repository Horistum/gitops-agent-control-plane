"""Pure execution decisions shared by the reference and production adapters.

Model notes are bounded, revision-bound DATA. They never authorize effects or
serve as verification evidence. All functions return new values, not mutations.
"""
from __future__ import annotations

import copy
import hashlib
import json

from .decisions import CoreError

__all__ = [
    "model_call_action",
    "context_checkpoint", "context_files", "context_view", "fingerprint",
    "next_attempt", "next_phase", "recovery_actions", "repair_target",
    "retirement", "retry_preconditions", "upgrade_boundary",
    "verification_transition",
]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def context_checkpoint(previous, *, revision, phase, summary, sources, requests, facts,
                       max_entries=8, max_sources=128, turn_id=None):
    """Retain conclusions and provenance across bounded source replacement.

    Source fingerprints describe what the model actually received, including
    omissions. Repeating a request after a changed response is legitimate; asking
    again with the same available input is a detectable absence of progress.
    """
    if any(type(value) is not int or value < 1 for value in (max_entries, max_sources)):
        raise CoreError("Context retention limits must be positive integers")
    old = previous if isinstance(previous, dict) and previous.get("revision") == revision else {}
    if turn_id is not None and old.get("turn_id") == turn_id:
        return copy.deepcopy(old)
    rows = copy.deepcopy(old.get("entries", []))
    index = dict(old.get("sources", {}))
    for path, value in sources.items():
        index[path] = {k: value[k] for k in ("sha256", "missing", "omitted", "binary", "excerpt") if k in value}
    request_hash = fingerprint({"requests": requests, "facts": facts, "sources": sources})
    repeats = old.get("repeats", 0) + 1 if old.get("request_hash") == request_hash else 0
    rows.append({"phase": phase, "summary": str(summary)[:2400],
                 "source_paths": list(sources)[:max_sources], "request_hash": request_hash})
    return {"revision": revision, "entries": rows[-max_entries:],
            "sources": dict(list(index.items())[-max_sources:]),
            "request_hash": request_hash, "repeats": repeats, "turn_id": turn_id}


def context_view(checkpoints, phase, revision):
    value = checkpoints.get(phase, {})
    return copy.deepcopy(value) if value.get("revision") == revision else {}


def context_files(required, requested, previous, limit):
    """Prioritize fresh requests while retaining earlier files within the bound."""
    if type(limit) is not int or limit < 0:
        raise CoreError("Context file limit must be a nonnegative integer")
    required = list(dict.fromkeys(required))
    if len(required) > limit:
        raise CoreError("Required source set exceeds the context file limit")
    ordered = list(dict.fromkeys(required + list(requested) + list(previous)))
    return ordered[:limit], ordered[limit:]


def repair_target(phase, verdict, findings):
    architectural = any(f.get("kind") in {"architecture", "scope"} and
                        f.get("severity") in {"medium", "high", "critical"} for f in findings)
    if verdict == "replan" or architectural or phase == "architect":
        return "architect"
    if phase in {"test_design", "tester"}:
        return phase
    if phase == "chief_plan":
        blocking = [f for f in findings if f.get("severity") in {"medium", "high", "critical"}]
        return "test_design" if blocking and all(f.get("kind") in {"testing", "evidence"} for f in blocking) else "architect"
    return "developer"


def next_phase(phase, *, level="high", challenge=False, return_phase=None):
    """Compatibility API; the workflow aggregate owns the only phase graph."""
    from .workflow import workflow_transition
    return workflow_transition({"phase": phase, "risk": level, "challenge": challenge,
                                "return_phase": return_phase}, {"kind": "advance"})["phase"]


def verification_transition(phase, passed, *, failure_kind=None):
    """Compatibility API for adapters upgrading to workflow events."""
    from .workflow import workflow_transition
    if failure_kind is None:
        failure_kind = "unavailable" if phase == "ci" else "product"
    return workflow_transition({"phase": phase, "risk": "high"},
        {"kind": "verification", "passed": passed, "failure_kind": failure_kind})["phase"]


def retry_preconditions(*, baseline, regressions, negative_control):
    if any(type(v) is not bool for v in (baseline, regressions, negative_control)):
        raise CoreError("Retry preconditions must be observed booleans")
    if not baseline or not regressions:
        return "FAILED_VERIFICATION"
    if not negative_control:
        return "BLOCKED_POLICY"
    return "ready"


def recovery_actions(task, limits):
    held = task.get("phase") == "await_human" and not task.get("pending")
    budget = task.get("agent_budget", {}).get("used", task.get("agent_calls", 0))
    exhausted = (task.get("context_rounds", 0) >= limits.get("max_context_rounds", 8) or
                 budget >= limits.get("max_agent_calls_per_task", 18) or
                 task.get("failure_code") in {"CONTEXT_STALLED", "EVIDENCE_UNAVAILABLE", "PROMPT_LIMIT", "PROTOCOL_LIMIT"})
    return {"retry": bool(held and not task.get("approvable") and task.get("retryable", True) and
                          task.get("hold_kind") in {"FAILED", "BLOCKED_POLICY"} and not exhausted),
            "replan": bool(held and not task.get("merge_sha") and
                           task.get("owner_replans", 0) < limits.get("max_owner_replans", 2))}


def model_call_action(*, receipt_available, dispatch_state):
    """Transport-independent rule; missing evidence never proves no dispatch."""
    if type(receipt_available) is not bool or dispatch_state not in {"not_started", "dispatched", "legacy_unknown"}:
        raise CoreError("Invalid model effect observation")
    if receipt_available:
        return "reuse"
    return "execute" if dispatch_state == "not_started" else "hold"


def next_attempt(current, archived=()):
    values = [1 if current is None else current] + [row.get("attempt", 1) for row in archived]
    if any(type(v) is not int or v < 1 for v in values):
        raise CoreError("Invalid task attempt identity")
    return max(values) + 1


def retirement(task, current, history, reason, *, status=None):
    """One archive/attempt rule for cancellation, reopen and upgrade adapters."""
    if task.get("pending"):
        raise CoreError("Cannot retire an attempt with a pending effect")
    previous = copy.deepcopy(task)
    if status:
        previous["phase"] = status
    following = next_attempt(current, list(history) + [previous])
    return {"previous": previous, "next_attempt": following,
            "record": {"task_id": task["id"], "goal_id": task.get("goal_id"),
                       "finished_at": task.get("finished_at"), "reason": reason, "task": previous}}


def upgrade_boundary(state, *, suspend=False):
    """Return an explicit migration intent only at a proven no-effect boundary."""
    if state.get("paused") is not True:
        raise CoreError("Upgrade requires authoritative paused=true")
    if (state.get("discovery_task") or {}).get("pending"):
        raise CoreError("Discovery still has a pending external effect")
    active = state.get("active")
    if not active:
        return {"suspend": None}
    task = state.get("tasks", {}).get(active, {})
    if not suspend:
        raise CoreError("Upgrade requires active=null or explicit suspension of an unchanged held attempt")
    if (task.get("phase") != "await_human" or task.get("pending") or task.get("pr") or
            task.get("merge_sha") or task.get("checkpoint_head") or task.get("base_refresh") or
            task.get("head") != task.get("base") or not task.get("base")):
        raise CoreError("Suspension requires a held unchanged attempt with no PR, checkpoint or pending effect")
    goal = state.get("goals", {}).get(task.get("goal_id"), {})
    if (goal.get("status") != "active" or state.get("active_goal") != task.get("goal_id") or
            task.get("goal_hash") != goal.get("hash")):
        raise CoreError("Suspension requires the exact active goal authority")
    return {"suspend": active, "task_hash": fingerprint(task)}
