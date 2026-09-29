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
    "verification_transition", "technical_recovery",
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
    index = copy.deepcopy(old.get("sources", {}))
    for path, value in sources.items():
        # File identity alone does not describe the excerpt the model actually saw.
        # Preserve omission/truncation and range metadata without retaining source text.
        index[path] = {k: copy.deepcopy(value[k]) for k in (
            "path", "sha256", "git_blob", "missing", "omitted", "binary", "excerpt",
            "truncated", "line_start", "line_end", "total_lines", "bytes", "reason") if k in value}
        text = value.get("text", value.get("content"))
        if isinstance(text, str) and not any(value.get(k) for k in ("missing", "omitted", "binary")):
            observed = text.encode("utf-8")
            index[path].update(observed_sha256=hashlib.sha256(observed).hexdigest(), observed_bytes=len(observed))
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
    """Legacy retry remains a rejected wire value; use typed recovery protocols.

    Technical outages use technical_recovery; completed verification uses the
    exact binding in reverification. A generic task flag grants neither action.
    """
    held = task.get("phase") == "await_human" and not task.get("pending")
    return {"retry": False,
            "replan": bool(held and not task.get("merge_sha") and
                           task.get("owner_replans", 0) < limits.get("max_owner_replans", 2))}


def technical_recovery(checkpoint, *, now, failure_kind=None, maximum=6,
                       initial_delay=30, retry_after=0):
    """Bound retries of trusted technical failures; text never grants recovery.

    Adapters must reconcile writes before retrying and classify a dispatched model
    without a receipt as unknown_effect. None observes an existing deadline only.
    The returned checkpoint is durable before another attempt; exhaustion is sticky.
    """
    if (type(maximum) is not int or not 1 <= maximum <= 20 or
            type(initial_delay) is not int or not 1 <= initial_delay <= 1800 or
            type(now) is not int or now < 0 or
            type(retry_after) is not int or not 0 <= retry_after <= 3600):
        raise CoreError("Invalid technical recovery bounds")
    kinds = {"transport", "not_dispatched"}
    if failure_kind is not None and (not isinstance(failure_kind, str) or failure_kind not in kinds | {
            "unknown_effect", "policy", "unclassified", "fenced"}):
        raise CoreError("Unknown technical recovery category")
    if not isinstance(checkpoint, dict):
        raise CoreError("Technical recovery checkpoint must be an object")
    state = {"attempts": checkpoint.get("attempts", 0),
             "next_attempt": checkpoint.get("next_attempt", 0),
             "exhausted": checkpoint.get("exhausted", False),
             "failure_kind": checkpoint.get("failure_kind")}
    if (type(state["attempts"]) is not int or not 0 <= state["attempts"] <= 21 or
            type(state["next_attempt"]) is not int or state["next_attempt"] < 0 or
            type(state["exhausted"]) is not bool or
            state["failure_kind"] is not None and
            (not isinstance(state["failure_kind"], str) or state["failure_kind"] not in kinds)):
        raise CoreError("Malformed technical recovery checkpoint")
    # Legacy checkpoints above the current bound remain exhausted after restart.
    state["exhausted"] = state["exhausted"] or state["attempts"] > maximum
    if failure_kind is not None and failure_kind not in kinds:
        action = "stop"
    elif state["exhausted"]:
        action = "exhausted"
    elif failure_kind is not None:
        state["attempts"] += 1
        state["failure_kind"] = failure_kind
        state["exhausted"] = state["attempts"] > maximum
        delay = max(retry_after, min(1800, initial_delay * 2 ** min(state["attempts"] - 1, 10)))
        state["next_attempt"] = now + delay
        action = "exhausted" if state["exhausted"] else "wait"
    elif state["next_attempt"] > now:
        action = "wait"
    else:
        action = "retry" if state["attempts"] else "ready"
    return {"action": action, "checkpoint": state,
            "retry": action in {"ready", "retry", "wait"},
            "delay": max(0, state["next_attempt"] - now) if action == "wait" else 0,
            "attempt": state["attempts"]}


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
