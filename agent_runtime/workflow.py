"""Translate operational storage to the shared workflow contract."""
from control_plane_core import (evidence_status_valid, require_workflow_evidence,
                                workflow_transition)
from .contracts import criteria


def snapshot(engine, phase=None):
    task = engine.task
    return {"phase": phase or task["phase"], "risk": task["risk"],
            "adaptive": engine.policy.get("adaptive_agent_graph", True),
            "critical": task.get("critical", False), "challenge": engine.policy["challenge"],
            "completed": task.get("completed_phases", []), "return_phase": task.get("risk_gate_return"),
            "merge_sha": task.get("merge_sha")}


def transition(engine, event, phase=None):
    task = engine.task
    result = workflow_transition(snapshot(engine, phase), event)
    task.update(phase=result["phase"], risk=result["risk"], critical=result.get("critical", False),
                completed_phases=result["completed"], workflow_contract=result["contract"])
    task.pop("risk_gate_return", None)
    if result.get("return_phase"):
        task["risk_gate_return"] = result["return_phase"]
    for group in result["invalidated"]:
        if group == "reviews":
            for role in ("reviewer", "challenge_review", "architect_accept", "chief_accept"):
                task["role_results"].pop(role, None)
        else:
            fields = {"candidate": ("candidate_evidence", "acceptance", "obligations"),
                      "ci": ("ci_evidence", "integration_evidence", "integration_obligations"),
                      "approval": ("approval", "approval_required"), "baseline": ("baseline", "independent_baseline"),
                      "work_authorization": ("work_approval", "work_approval_required"),
                      "plan": ("plan", "working_set"), "test_design": ("test_design",),
                      "context": ("memory", "requested_files", "search_results")}
            for field in fields.get(group, ()):
                task.pop(field, None)
    return result


def require_evidence(engine, stage="candidate"):
    task = engine.task
    revision = {key: task[key] for key in ("head", "base", "spec_hash")}
    reviews = {}
    for phase, row in task.get("role_results", {}).items():
        evidence = row.get("acceptance_evidence", [])
        expected = criteria(engine.item())
        passed = len(evidence) == len(expected) and {x["criterion_id"] for x in evidence} == {x["id"] for x in expected}
        passed = passed and all(evidence_status_valid(c, next(x for x in evidence if x["criterion_id"] == c["id"])) for c in expected)
        reviews[phase] = {**row, "acceptance_passed": passed}
    proof = task.get("candidate_evidence", {})
    state = {**snapshot(engine), "revision": revision, "proofs": {
        "candidate": proof, "independent": proof, "reviews": reviews,
        "acceptance": task.get("obligations", {}),
        "ci": {**revision, "passed": task.get("integration_obligations", {}).get("passed") is True},
        "merge": {"sha": task.get("merge_sha"), "parents": task.get("merge_parents", [])},
        "postmerge": {**task.get("postmerge_evidence", {}), "complete": task.get("obligations", {}).get("complete") is True}}}
    return require_workflow_evidence(state, stage)
