"""Role proposals, scope gates and bounded repair; no fixture source templates."""
from __future__ import annotations

from control_plane_core import (evidence_status_valid, fingerprint, merge_authority, path_allowed,
                                repair_target, risk_rank, test_criteria, validate_bindings)
from .contracts import criteria
from .io import Closed


def repair(engine, target, feedback):
    task = engine.task
    if task.get("merge_sha") or task.get("pr"):
        raise Closed("Published/merged candidate requires reconciliation before a new attempt")
    if task["repairs"] >= engine.policy["limits"]["repairs"]:
        raise Closed("Bounded repair budget exhausted")
    task["repairs"] += 1
    task["feedback"].append(feedback)
    task["phase"] = target
    task.pop("approval", None)
    for name in ("candidate_evidence", "ci_evidence", "acceptance", "obligations"):
        task.pop(name, None)
    for phase in ("reviewer", "challenge_review", "architect_accept", "chief_accept"):
        task["role_results"].pop(phase, None)


def role_step(engine):
    task, policy = engine.task, engine.policy
    phase = task["phase"]
    if phase == "tester" and task["frozen_tests"]:
        edits = task["frozen_tests"]["edits"]
        if all(engine.repo.read(task["head"], row["path"]) == row["content"].encode() for row in edits):
            engine.advance()
        elif all(engine.repo.read(task["head"], row["path"]) is None for row in edits):
            task["proposal"] = {"edits": edits, "bindings": task["frozen_tests"]["bindings"]}
            task["phase"] = "apply_tester"
        else:
            raise Closed("Retained test paths conflict with the new candidate")
        return
    output = engine.model(phase, task)
    if output is None:
        return
    task["risk"] = max((task["risk"], output["risk"]), key=risk_rank)
    authority = merge_authority(task["risk"], risk_ceiling=engine.goal["risk_ceiling"],
                                auto_merge_ceiling=engine.goal["auto_merge_ceiling"])
    if authority["blocked"]:
        raise Closed("Model assessed risk exceeds hard goal ceiling")
    blocking = [row for row in output["findings"] if row["severity"] in {"medium", "high", "critical"}]
    if output["verdict"] == "blocked":
        engine.hold(output["summary"], kind="FAILED")
        return
    if output["verdict"] in {"fix", "replan"} or blocking:
        repair(engine, repair_target(phase, output["verdict"], output["findings"]),
               {"phase": phase, "summary": output["summary"], "findings": output["findings"]})
        return
    if output["verdict"] != "ready":
        raise Closed("Unsupported role transition")
    if phase in {"reviewer", "challenge_review", "architect_accept", "chief_accept"}:
        expected = criteria(engine.item())
        rows = output["acceptance_evidence"]
        if len(rows) != len(expected) or {row["criterion_id"] for row in rows} != {row["id"] for row in expected}:
            raise Closed("Role must explicitly assess every acceptance criterion")
        if not all(evidence_status_valid(criterion, next(row for row in rows if row["criterion_id"] == criterion["id"])) for criterion in expected):
            raise Closed("Role acceptance claims evidence from an unavailable stage")
    if phase == "architect":
        working = output["working_set"]
        if not working or len(set(working)) != len(working) or any(
                not path_allowed(path, policy["allowed_paths"], policy["protected_paths"] + policy["test_paths"],
                                 [".github/*", ".agent-control/*", "AGENTS.md"]) for path in working):
            raise Closed("Architect working set exceeds source authority")
        task["working_set"], task["plan"] = working, output["steps"]
    elif phase == "test_design":
        ids = {row["id"] for row in test_criteria(criteria(engine.item()))}
        if {row["criterion_id"] for row in output["scenarios"]} != ids:
            raise Closed("Test design must cover every executable criterion")
        task["test_design"] = output["scenarios"]
    elif phase in {"developer", "tester"}:
        if phase == "tester":
            validate_bindings([row["id"] for row in test_criteria(criteria(engine.item()))], output["bindings"])
            for criterion in test_criteria(criteria(engine.item())):
                modes = {row["mode"] for row in output["bindings"] if row["criterion_id"] == criterion["id"]}
                if ((criterion["kind"] == "behavior" and "new_behavior" not in modes)
                        or (criterion["kind"] == "compatibility" and modes != {"regression"})):
                    raise Closed("Test binding mode contradicts owner-authored criterion type")
        task["proposal"] = output
        task["phase"] = "apply_" + phase
        return
    engine.advance()


def apply_step(engine):
    task, policy = engine.task, engine.policy
    role = task["phase"].removeprefix("apply_")
    output = task["proposal"]
    tester = role == "tester"
    edits = output["edits"]
    protected = policy["protected_paths"] + ([] if tester else policy["test_paths"])
    request = {"parent": task["head"], "edits": edits, "role": role}
    result = engine.store.effect("commit", request, lambda identity: {"head": engine.repo.commit(
        task["head"], edits, identity, allowed=policy["test_paths"] if tester else policy["allowed_paths"],
        protected=protected, working_set=None if tester else task["working_set"],
        additions_only=tester, maximum=policy["limits"]["edit_bytes"])})
    if tester:
        task["production_head"] = task["head"]
    task["head"] = result["head"]
    # Retain candidate objects across interruption and rejected attempts.
    engine.repo.text("update-ref", "refs/heads/agent/" + engine.state["run_id"] + "/" + task["id"] +
                     "/" + str(task["attempt"]), task["head"])
    if tester:
        task["proposed_tests"] = {"edits": edits, "bindings": output["bindings"], "hash": fingerprint(edits)}
    task.pop("proposal")
    engine.advance(role)
