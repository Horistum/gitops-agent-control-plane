"""Read-only operator guidance. It cannot authorize or execute an action.

The exact decision is kept intact. Logs, Git observations and presentation hints
are deliberately outside its hash; every action still rechecks the saved state.
"""
from __future__ import annotations

import shlex
import re

from control_plane_core import CoreError, fingerprint, graph_level, upgrade_boundary, workflow_transition
from .decisions import decision_document
from .diagnostics import recent_events, recovery_steps, safe_text
from .io import Closed
from .observations import status_document
from .usage import usage_report

COMMAND_HELP = {
    "start": "Start and drive a new authorized run.",
    "doctor": "Check configured dependencies before starting; no model call.",
    "resume": "Drive an existing run until it stops; does not clear holds or pause.",
    "serve": "Supervise a run with bounded polling.",
    "backup": "Back up a paused, quiescent run.",
    "restore": "Restore a verified backup into a new run directory.",
    "registry": "List the status of local runs.",
    "status": "Observe progress, blocker and the run-owned product repository.",
    "decision": "Inspect the exact candidate, evidence and available owner actions.",
    "explain": "Explain what happened, why, where the result is and what to do next.",
    "tick": "Execute one controller step; does not clear a hold or pause.",
    "usage": "Inspect model reservations and receipt-derived usage.",
    "diagnostics": "Read recent diagnostic events.",
    "review": "Open the authenticated local operator and candidate review UI.",
    "pause": "Stop advancement without changing the runtime binding.",
    "continue": "Remove pause or explicitly renew an exhausted technical retry episode.",
    "approve": "Authorize the exact candidate binding after reviewing its evidence.",
    "approve-work": "Authorize the accepted work plan, scenarios and source scope for this attempt.",
    "retry": "Retired command; use a displayed bound reverify or technical continue action.",
    "reverify": "Repeat completed verification against unchanged source, scope and frozen assertions; no model replay.",
    "reconcile": "Resume a replay-safe pending non-model effect.",
    "reconcile-effect": "Consume the original receipt of an exact pending model call; no new call.",
    "retry-effect": "Abandon an uncertain model call and allow a replacement; possible duplicate cost.",
    "replan": "Retire the current attempt and plan again within the existing budget.",
    "cancel": "Retire unmerged work; merged work still requires postmerge verification.",
    "upgrade": "Accept new runtime bytes only at a paused, quiescent boundary.",
}

PHASE_LABELS = {
    "reconcile": "Select authorized work", "baseline": "Verify starting code",
    "architect": "Plan source changes", "test_design": "Design independent tests",
    "chief_plan": "Review the plan", "developer": "Propose source changes",
    "apply_developer": "Apply source changes", "verify": "Verify candidate",
    "tester": "Propose independent tests", "apply_tester": "Apply independent tests",
    "independent_baseline": "Check tests against original code",
    "independent_verify": "Check tests against candidate", "reviewer": "Review candidate",
    "challenge_review": "Challenge the review", "architect_accept": "Accept architecture",
    "chief_accept": "Final high-risk review", "publish": "Publish candidate",
    "ci": "Verify integration", "merge": "Merge exact candidate",
    "postmerge": "Verify merged result", "done": "Finish item", "await_human": "Await owner decision",
}


def workflow_path(*, risk="low", adaptive=True, critical=False, challenge=False):
    """Derive the normal route from the actual reducer, never a second graph."""
    frame = {"phase": "baseline", "risk": risk, "adaptive": adaptive,
             "critical": critical, "challenge": challenge}
    phases = []
    for _ in range(64):
        phase = frame["phase"]
        if phase in phases:
            raise Closed("Workflow route unexpectedly loops")
        phases.append(phase)
        if phase == "done":
            return phases
        frame = workflow_transition(frame, {"kind": "advance"})
    raise Closed("Workflow route exceeds presentation limit")


def workflow_document(state):
    task = state.get("task")
    if not task:
        return {"current": state["phase"], "phases": [],
                "note": "No active item. See recorded transitions and the merged result." if state["status"] in {"COMPLETED", "CANCELLED"}
                        else "An item-specific route appears after discovery selects authorized work."}
    modifiers = {"risk": task["risk"], "adaptive": state["policy"].get("adaptive_agent_graph", True),
                 "critical": task.get("critical", False), "challenge": state["policy"]["challenge"]}
    route = []
    for phase in workflow_path(**modifiers):
        route.append(phase)
        if phase in {"developer", "tester"}:
            route.append("apply_" + phase)
    return {"current": task["phase"], "resume_phase": task.get("resume_phase"),
            "risk_gate_return": task.get("risk_gate_return"), **modifiers,
            "level": graph_level(modifiers),
            "phases": [{"id": phase, "label": PHASE_LABELS.get(phase, phase),
                        "current": phase == task["phase"],
                        "resume": task["phase"] == "await_human" and phase == task.get("resume_phase")}
                       for phase in route],
            "note": "Required normal route, not a completion percentage. Repairs, escalation and holds can revisit phases."}


def _command(root, name, *args):
    return shlex.join(["agent-control", name, "--state", str(root), *args])


def evidence_summary(name, proof):
    if name == "independent_baseline":
        return "Negative control observation; expected failures may be required. Inspect the bound test identities."
    passed = proof.get("passed") if isinstance(proof, dict) else None
    return "Passed" if passed is True else "Failed" if passed is False else "Recorded; inspect the observations"


def action_guidance(store, decision):
    state, root = store.state, store.root.resolve()
    pending, task = state.get("pending") or {}, state.get("task") or {}
    code = (decision.get("diagnostic") or {}).get("code")
    unstarted = pending.get("kind") == "model" and pending.get("dispatch_state") == "not_started"
    technical_continue = decision.get("technical_continue_allowed", False)
    receipt = None
    if pending.get("kind") == "model" and not unstarted:
        if not re.fullmatch(r"[0-9a-f]{64}", pending.get("id", "")):
            raise Closed("Invalid pending model effect identity")
        # Existence is not validation. Only reconcile-effect may establish that
        # the complete receipt, request and current execution frame agree.
        receipt = {"path": str(root / "receipts" / (pending["id"] + ".json")),
                   "present": (root / "receipts" / (pending["id"] + ".json")).is_file(),
                   "note": "Presence only; reconciliation validates the exact request and receipt."}
    actions = []
    for name in decision["actions"] + ([decision["approval_action"]] if decision["approvable"] else []):
        args = []
        condition = "The controller rechecks the current state before executing."
        enabled = True
        if name in {"reconcile-effect", "retry-effect"}:
            args = ["--binding", pending["id"]]
            if name == "reconcile-effect":
                enabled = receipt["present"]
                condition = ("Requires the original valid receipt for this exact call." if enabled else
                             "The original receipt is missing. Restore it before reconciliation.")
            else:
                enabled = not receipt["present"] and state["model_calls"] < state["policy"]["limits"]["model_calls"]
                condition = "Explicit owner choice: the previous call may already have been charged. The lifetime budget is unchanged."
                if receipt["present"]:
                    condition = "A receipt is present; reconcile it instead of repeating the call."
                elif not enabled:
                    condition = "No model-call budget remains. Retrying cannot reset it."
        elif name in {"approve", "approve-work"}:
            args = ["--binding", decision["binding"], "--decision-hash", decision["decision_hash"]]
            condition = ("Review the plan, test scenarios and working files before authorizing work."
                         if name == "approve-work" else "Review the exact candidate, findings and evidence before approval.")
        elif name == "reverify":
            args = ["--binding", decision["reverification_binding"], "--decision-hash", decision["decision_hash"]]
            condition = "Re-observe this exact failed verification after correcting its external cause. All lifetime budgets and old receipts are preserved."
        elif name == "replan":
            condition = "Inspect the failure and correct its cause first. The model budget is not reset."
        elif name == "continue":
            condition = ("Explicitly renews this exhausted technical retry episode while preserving its pending effect and lifetime budgets."
                         if technical_continue else "Only removes pause. A hold still requires its own recovery action.")
        elif name == "reconcile":
            condition = "Resume only the recorded replay-safe non-model effect; then run one tick."
        if state["status"] in {"COMPLETED", "CANCELLED"}:
            enabled = False
            condition = "This run is terminal; no recovery step is required."
        actions.append({"id": name, "label": name, "description": COMMAND_HELP[name],
                        "command": _command(root, name, *args), "condition": condition, "enabled": enabled})

    if code == "RUNTIME_CHANGED" and state["paused"] and not pending and not state.get("owner_intent"):
        view = {"paused": True, "active": task.get("id"), "tasks": {task["id"]: task} if task else {},
                "active_goal": state["goal"]["id"], "goals": {state["goal"]["id"]:
                    {"status": "active", "hash": fingerprint(state["goal"])}}}
        for suspend in (False, True):
            try:
                upgrade_boundary(view, suspend=suspend)
            except CoreError:
                continue
            actions.append({"id": "upgrade", "label": "upgrade", "description": COMMAND_HELP["upgrade"],
                "command": _command(root, "upgrade", *(["--suspend"] if suspend else [])), "enabled": True,
                "condition": "Explicitly retires this eligible unchanged held attempt." if suspend else
                             "No pending effect or active task; keeps the run paused."})
            break
    if (code not in {"RUNTIME_CHANGED", "AUTHORITY_CHANGED"} and (not pending or unstarted)
            and not state["paused"] and state["status"] in {"RUNNING", "WAITING_EXTERNAL"}):
        actions.append({"id": "tick", "label": "Run one step", "description": COMMAND_HELP["tick"],
                        "command": _command(root, "tick"), "enabled": True,
                        "condition": "The model was not dispatched; retain its reservation and retry after the persisted technical deadline."
                                     if unstarted else "Restore the unavailable dependency first." if state["status"] == "WAITING_EXTERNAL"
                                     else "May execute work and reserve a model call within the authorized budget."})

    preferred = None
    if state["status"] not in {"COMPLETED", "CANCELLED"}:
        if code == "RUNTIME_CHANGED":
            preferred = "upgrade" if state["paused"] else "pause"
        elif code != "AUTHORITY_CHANGED":
            if technical_continue:
                preferred = "continue"
            elif pending and not unstarted:
                # Never recommend another paid dispatch as the default recovery.
                preferred = "reconcile-effect" if pending["kind"] == "model" else "reconcile"
            elif decision["approvable"]:
                preferred = decision["approval_action"]
            elif state["status"] in {"RUNNING", "WAITING_EXTERNAL"}:
                preferred = "continue" if state["paused"] else "tick"
            elif state["status"] == "FAILED":
                preferred = "reverify"
            elif code in {"DISCOVERY_NOT_SELECTED", "CONTEXT_LIMIT"}:
                preferred = "replan"
    recommendation = next((row for row in actions if row["id"] == preferred and row["enabled"]), None)
    return actions, recommendation, receipt


def explanation_document(store, limit=10):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise Closed("Explanation limit must be between 1 and 100")
    state = store.state
    decision = decision_document(state)
    status = status_document(state, store.root)
    diagnostic = decision["diagnostic"]
    actions, next_action, receipt = action_guidance(store, decision)
    message = (diagnostic or {}).get("message") or state.get("reason")
    if not message:
        message = {"COMPLETED": "The authorized goal is complete; inspect the merged result in the run repository.",
                   "CANCELLED": "This run was cancelled.",
                   "RUNNING": "The run is ready for its next controller step.",
                   "WAITING_EXTERNAL": "The run is waiting for an external dependency.",
                   "NEEDS_DECISION": "The exact candidate requires owner review."}.get(state["status"], "The run is held; inspect the current decision.")
    if state.get("pending") and not diagnostic:
        message = ("A reserved model call was not dispatched. Retry after its persisted technical deadline."
                   if state["pending"].get("dispatch_state") == "not_started" else
                   "A model effect is pending. Its outcome must be established from the original receipt before continuing."
                   if receipt else "A replay-safe non-model effect is pending and must be reconciled.")
    if state["paused"]:
        message = "Advancement is paused. " + message
    guidance = recovery_steps((diagnostic or {}).get("code"), state) if diagnostic or state.get("pending") else []
    warnings = []
    try:
        log = recent_events(store.root, limit)
    except Exception as exc:
        log = {"events": [], "log": "diagnostics.jsonl"}
        warnings.append("Diagnostic history unavailable: " + safe_text(exc))
    try:
        usage = usage_report(store)
        usage = {key: usage[key] for key in ("reserved_calls", "recorded_calls", "unknown_outcomes",
                                           "not_dispatched", "reported_tokens", "calls_without_usage", "billing_ready")}
    except Exception as exc:
        usage = {"reserved_calls": state["model_calls"], "recorded_calls": None, "unknown_outcomes": None}
        warnings.append("Receipt-derived usage unavailable: " + safe_text(exc))
    history = state.get("history", [])
    timeline = [{"sequence": i + 1, **row} for i, row in enumerate(history) if i >= len(history) - limit]
    return {"schema": 1, "run_id": state["run_id"], "revision": state.get("revision", 0),
            "summary": safe_text(message), "phase_label": PHASE_LABELS.get(status["phase"], status["phase"]),
            "status": status, "decision": decision, "diagnostic": diagnostic,
            "next_action": next_action, "guidance": guidance, "actions": actions, "pending_receipt": receipt,
            "workflow": workflow_document(state), "timeline": timeline,
            "timeline_note": "Recent recorded transitions in order. Older entries may be trimmed; original events have no timestamps.",
            "recent_actions": decision["recent_actions"][-limit:], "diagnostics": log,
            "evidence_summaries": {name: evidence_summary(name, proof) for name, proof in decision["evidence"].items()},
            "usage": usage, "warnings": warnings,
            "observation_note": "Read-only explanation of one state revision. Git refs and log files are separate observations; reload before acting."}
