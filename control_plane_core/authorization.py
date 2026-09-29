"""Purpose-separated owner authority over a work plan and an exact candidate.

Adapters authenticate the owner and establish the scope/risk gates. These pure
bindings cannot grant authority, waive a gate, or turn historical approvals into
new authority. A work plan remains stable while its implementation head changes.
"""
from __future__ import annotations

from .execution import fingerprint

__all__ = ["work_authorization", "candidate_authorization"]


def _identity(task, policy, goal, critical_paths):
    return {"task": task["id"], "attempt": task.get("attempt", 1),
            "base": task["base"], "spec": task["spec_hash"], "goal": goal,
            "risk": task.get("risk"), "critical_paths": sorted(set(critical_paths)),
            "policy": policy}


def work_authorization(task, *, policy, goal, critical_paths=()):
    """Bind the accepted plan, including its authorized planned critical scope."""
    return fingerprint({"purpose": "work-plan/v1", **_identity(task, policy, goal, critical_paths),
                        "plan": task.get("plan", {}), "scenarios": task.get("scenarios", []),
                        "working_files": sorted(set(task.get("working_files", [])))})


def candidate_authorization(task, *, policy, goal, critical_paths=()):
    """Bind merge authority to the exact final candidate, independently of work."""
    return fingerprint({"purpose": "candidate-merge/v1", **_identity(task, policy, goal, critical_paths),
                        "head": task["head"]})
