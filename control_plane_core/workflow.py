"""The portable workflow aggregate: observations in, decisions out, no I/O.

Adapters authenticate observations and execute durable effects. They do not own a
second phase graph. A snapshot is a projection of the adapter's authoritative
task, not another persisted ledger. Decisions explicitly invalidate evidence;
notes and model verdicts never substitute for machine observations.
"""
from __future__ import annotations

import copy

from .decisions import CoreError, require_merge_identity, require_revision_identity, risk_rank

__all__ = ["WORKFLOW_CONTRACT", "graph_level", "required_reviews", "workflow_transition", "require_workflow_evidence"]

WORKFLOW_CONTRACT = "development-workflow/v1"
REASONING_PHASES = frozenset({"architect", "test_design", "chief_plan", "developer",
    "tester", "reviewer", "challenge_review", "architect_accept", "chief_accept"})
REVIEW_PHASES = ("reviewer", "challenge_review", "architect_accept", "chief_accept")


def graph_level(state):
    risk_rank(state.get("risk"))
    if type(state.get("adaptive", True)) is not bool:
        raise CoreError("Adaptive graph selection must be a boolean")
    return state["risk"] if state.get("adaptive", True) and not state.get("critical") else "high"


def required_reviews(state):
    level = graph_level(state)
    if type(state.get("challenge", False)) is not bool:
        raise CoreError("Challenge requirement must be an explicit boolean")
    roles = ["reviewer"]
    if state.get("challenge"):
        roles.append("challenge_review")
    if level != "low" or state.get("challenge"):
        roles.append("architect_accept")
    if level == "high":
        roles.append("chief_accept")
    return roles


def _following(phase, state):
    level = graph_level(state)
    challenge, returning = state.get("challenge", False), state.get("return_phase")
    if type(challenge) is not bool:
        raise CoreError("Challenge requirement must be an explicit boolean")
    if returning not in {None, "developer", "verify"}:
        raise CoreError("Risk review must resume implementation or verification")
    graph = {"baseline": "architect", "architect": "developer" if level == "low" else "test_design",
        "test_design": "chief_plan" if level == "high" else (returning or "developer"),
        "chief_plan": returning or "developer", "developer": "verify", "verify": "tester",
        "tester": "independent_baseline", "independent_baseline": "independent_verify",
        "independent_verify": "reviewer", "reviewer": "challenge_review" if challenge else
            ("publish" if level == "low" else "architect_accept"),
        "challenge_review": "architect_accept", "architect_accept": "chief_accept" if level == "high" else "publish",
        "chief_accept": "publish", "publish": "ci", "ci": "merge", "merge": "postmerge", "postmerge": "done"}
    if phase not in graph:
        raise CoreError("Unknown execution phase: " + str(phase))
    return graph[phase]


def workflow_transition(state, event):
    """Reduce one authenticated event against a task projection.

    ``advance`` means the adapter established the phase's preconditions, not a
    model claim of completion. Effect boundaries additionally call
    ``require_workflow_evidence``. ``invalidated`` names semantic evidence groups;
    adapters translate these to their storage format before persisting the task.
    """
    result = copy.deepcopy(state)
    phase, kind = state["phase"], event["kind"]
    graph_level(state)
    result["invalidated"] = []
    completed = set(state.get("completed", []))
    if kind == "advance":
        result["phase"] = _following(phase, state)
        if phase in REASONING_PHASES:
            completed.add(phase)
        if phase in {"test_design", "chief_plan"} and result["phase"] != "chief_plan":
            result.pop("return_phase", None)
    elif kind == "verification":
        passed = event.get("passed")
        if type(passed) is not bool:
            raise CoreError("Verification transition requires an observed boolean")
        if phase not in {"baseline", "verify", "independent_baseline", "independent_verify", "ci", "postmerge"}:
            raise CoreError("Unsupported verification phase")
        if passed:
            result["phase"] = _following(phase, state)
        elif phase == "independent_baseline":
            result["phase"] = "await_human" if event.get("frozen") else "tester"
        elif phase in {"verify", "independent_verify", "ci"} and event.get("failure_kind", "unavailable" if phase == "ci" else "product") == "product":
            result["phase"] = "developer"
        else:
            result["phase"] = "await_human"
    elif kind == "risk":
        if event.get("risk") is not None:
            result["risk"] = max((state["risk"], event["risk"]), key=risk_rank)
        result["critical"] = bool(state.get("critical") or event.get("critical"))
        level = graph_level(result)
        gates = (["test_design"] if level != "low" else []) + (["chief_plan"] if level == "high" else [])
        missing = next((gate for gate in gates if gate not in completed), None)
        if missing and phase not in {"baseline", "architect", missing}:
            returning = state.get("return_phase") or ("developer" if phase in {"test_design", "chief_plan", "developer"} else "verify")
            result.update(phase=missing, return_phase=returning)
            result["invalidated"] = ["candidate", "reviews", "ci", "approval", "work_authorization"]
    elif kind == "repair":
        target = event.get("target")
        if state.get("merge_sha"):
            raise CoreError("Merged work requires explicit remediation authority")
        if target not in {"architect", "test_design", "developer", "tester"}:
            raise CoreError("Unknown repair target")
        result["phase"] = target
        result.pop("return_phase", None)
        result["invalidated"] = ["candidate", "reviews", "ci", "approval"]
        completed.difference_update(REVIEW_PHASES)
        if target in {"architect", "test_design"}:
            completed.difference_update({"test_design", "chief_plan"})
            result["invalidated"].extend(["test_design", "work_authorization"])
        if target == "architect":
            completed.discard("architect")
            result["invalidated"].append("plan")
    elif kind == "base_changed":
        if state.get("merge_sha"):
            raise CoreError("Cannot rebase a merged attempt")
        result["phase"] = "baseline"
        result["invalidated"] = ["baseline", "candidate", "reviews", "ci", "approval", "work_authorization", "context"]
    else:
        raise CoreError("Unknown workflow event: " + str(kind))
    result["completed"] = sorted(completed)
    result["contract"] = WORKFLOW_CONTRACT
    return result


def require_workflow_evidence(state, stage):
    """One release gate for every adapter, against current typed observations.

    Evidence keys are normalized by the adapter after provider authentication.
    Model assessments and machine observations are kept in separate fields.
    Receipt binding is exact, including base and spec (a matching head alone is
    insufficient). Future obligations become due only at their defined stage.
    """
    if stage not in {"candidate", "integration", "postmerge"}:
        raise CoreError("Unknown workflow evidence stage")
    revision = state["revision"]
    keys = ("head", "base", "spec_hash")
    if any(not isinstance(revision.get(k), str) or not revision[k] for k in keys):
        raise CoreError("Workflow evidence requires an exact revision")
    commits = {key: revision[key] for key in ("head", "base")}
    require_revision_identity(commits, commits)
    proofs = state.get("proofs", {})
    for name in ("candidate", "independent"):
        proof = proofs.get(name, {})
        if any(proof.get(k) != revision[k] for k in keys) or proof.get("passed") is not True:
            raise CoreError("Missing or stale workflow observation: " + name)
    if proofs.get("acceptance", {}).get("passed") is not True:
        raise CoreError("Candidate acceptance obligations remain unsatisfied")
    for role in required_reviews(state):
        proof = proofs.get("reviews", {}).get(role, {})
        if any(proof.get(k) != revision[k] for k in keys) or proof.get("verdict") != "ready":
            raise CoreError("Missing or stale independent verdict: " + role)
        if proof.get("acceptance_passed") is not True:
            raise CoreError("Acceptance evidence incomplete: " + role)
    if stage in {"integration", "postmerge"}:
        ci = proofs.get("ci", {})
        if any(ci.get(k) != revision[k] for k in keys) or ci.get("passed") is not True:
            raise CoreError("Current integration obligations remain unsatisfied")
    if stage == "postmerge":
        merged, receipt = proofs.get("merge", {}), proofs.get("postmerge", {})
        require_merge_identity(revision["base"], revision["head"], merged.get("parents", []))
        if (not merged.get("sha") or receipt.get("head") != merged["sha"] or
                any(receipt.get(k) != revision[k] for k in ("base", "spec_hash")) or
                receipt.get("passed") is not True or receipt.get("complete") is not True):
            raise CoreError("Merged product lacks complete current verification")
    return True
