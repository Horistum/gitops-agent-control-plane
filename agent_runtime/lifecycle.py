"""Observed verification, staged acceptance, exact publication and completion."""
from __future__ import annotations

from control_plane_core import (acceptance_evidence, completion_transition, evaluate_obligations,
    fingerprint, merge_authority, path_allowed, require_merge_identity, require_revision_identity,
    test_criteria, test_failure_kind, verification_transition)
from .contracts import criteria
from .io import Closed, Unavailable, digest
from .roles import repair


def observe(engine, phase, head, *, external=False):
    task = engine.task
    request = {"phase": phase, "head": head, "base": task["base"], "spec_hash": task["spec_hash"], "external": external}
    return engine.store.effect("verify", request, lambda _: engine.verification.observe(
        engine.repo, head, task["base"], task["spec_hash"], cases=external))


def preserved(task, receipt):
    required = set(task["baseline"]["junit"]["executed_identities"])
    return required <= set(receipt["junit"]["executed_identities"])


def frozen_intact(engine, head):
    frozen = engine.task["frozen_tests"]
    return frozen is not None and all(engine.repo.read(head, edit["path"]) == edit["content"].encode() for edit in frozen["edits"])


def observations(engine, receipt, stage):
    task = engine.task
    bindings = task["frozen_tests"]["bindings"]
    test_results = acceptance_evidence([row["id"] for row in test_criteria(criteria(engine.item()))],
                                       bindings, task["independent_baseline"], receipt)
    if not test_results["passed"] or not preserved(task, receipt):
        raise Closed("Independent evidence or retained baseline identities failed")
    result = {}
    changed = engine.repo.changed(task["base"], receipt["head"])
    for row in criteria(engine.item()):
        kind = row["kind"]
        if kind in {"behavior", "compatibility"}:
            result[row["id"]] = all(x["passed"] for x in test_results["rows"] if x["criterion_id"] == row["id"])
        elif kind == "documentation":
            result[row["id"]] = all(path in changed and bool((engine.repo.read(receipt["head"], path) or b"").strip()) for path in row["paths"])
        elif kind == "ci":
            result[row["id"]] = bool(engine.github and task.get("ci_evidence", {}).get("passed") and
                ("integration" not in row["targets"] or task.get("integration_evidence", {}).get("passed")))
        else:
            result[row["id"]] = bool(stage == "postmerge" and task.get("merge_sha") == receipt["head"])
    return result, test_results


def verification_step(engine):
    task, phase = engine.task, engine.task["phase"]
    if phase == "independent_baseline":
        tests = task["frozen_tests"] or task["proposed_tests"]
        result = engine.store.effect("negative-control-commit", {"base": task["base"], "tests": tests},
            lambda identity: {"head": engine.repo.commit(task["base"], tests["edits"], identity,
                allowed=engine.policy["test_paths"], protected=engine.policy["protected_paths"], additions_only=True,
                maximum=engine.policy["limits"]["edit_bytes"])})
        receipt = observe(engine, phase, result["head"])
        failures = set(receipt["junit"]["failed_identities"])
        expected = {row["test_id"] for row in tests["bindings"] if row["mode"] == "new_behavior"}
        executed = set(receipt["junit"]["executed_identities"])
        valid = (not receipt["junit"]["error_identities"] and failures == expected and preserved(task, receipt)
                 and all(row["test_id"] in executed for row in tests["bindings"])
                 and (not expected or any(row["exit_code"] != 0 for row in receipt["commands"])))
        if not valid:
            if task["frozen_tests"]:
                engine.hold("Previously accepted negative control no longer holds; frozen tests require diagnosis")
            else:
                task["head"] = task["production_head"]
                task.pop("proposed_tests", None)
                repair(engine, verification_transition(phase, False), {"phase": phase, "observation": receipt})
            return
        task["frozen_tests"] = tests
        task["independent_baseline"] = receipt
        engine.advance()
        return
    receipt = observe(engine, phase, task["head"], external=phase == "independent_verify")
    if phase == "baseline":
        if not receipt["passed"]:
            engine.hold("Original product baseline failed; no model implementation can repair undeclared work")
            return
        task["baseline"] = receipt
        task["phase"] = verification_transition(phase, True)
        return
    if not receipt["passed"] or not preserved(task, receipt):
        target = verification_transition(phase, False, failure_kind=test_failure_kind(receipt))
        if target == "developer" and preserved(task, receipt):
            repair(engine, target, {"phase": phase, "observation": receipt})
        else:
            engine.hold("Ambiguous verification or missing retained identities; diagnosis required")
        return
    if phase == "independent_verify":
        if not frozen_intact(engine, task["head"]):
            raise Closed("Frozen independent tests changed")
        results, evidence = observations(engine, receipt, "candidate")
        task["acceptance"] = evidence
        task["candidate_evidence"] = receipt
        task["obligations"] = evaluate_obligations(criteria(engine.item()), results, stage="candidate")
        if not task["obligations"]["passed"]:
            repair(engine, "developer", {"phase": phase, "obligations": task["obligations"]})
            return
    engine.advance()


def candidate_gate(engine):
    task = engine.task
    receipt = task.get("candidate_evidence", {})
    require_revision_identity({"head": task["head"], "base": task["base"]}, receipt)
    if receipt.get("spec_hash") != task["spec_hash"] or not receipt.get("passed") or not task.get("obligations", {}).get("passed"):
        raise Closed("Candidate lacks current acceptance evidence")
    if not frozen_intact(engine, task["head"]):
        raise Closed("Frozen tests differ from reviewed candidate")
    frozen_paths = {row["path"] for row in task["frozen_tests"]["edits"]}
    if set(engine.repo.changed(task["base"], task["head"])) - set(task["working_set"]) - frozen_paths:
        raise Closed("Final diff exceeds the current architect working set")
    required = ["reviewer", "architect_accept", "chief_accept"] + (["challenge_review"] if engine.policy["challenge"] else [])
    for phase in required:
        review = task["role_results"].get(phase, {})
        if review.get("head") != task["head"] or review.get("verdict") != "ready":
            raise Closed("Missing current model review: " + phase)
    current = engine.repo.remote_base() if engine.github else engine.repo.resolve(engine.policy["base_branch"])
    if current != task["base"]:
        raise Closed("Base moved; replan/rebase must invalidate old evidence before publication or merge")


def lifecycle_step(engine):
    task, phase = engine.task, engine.task["phase"]
    if phase in {"baseline", "verify", "independent_baseline", "independent_verify"}:
        verification_step(engine)
    elif phase == "publish":
        candidate_gate(engine)
        if engine.github:
            branch = "agent/" + engine.state["run_id"] + "/" + task["id"] + "/" + str(task["attempt"])
            task["pr"] = engine.store.effect("publish", {"head": task["head"], "base": task["base"], "branch": branch},
                lambda _: engine.github.publish(engine.repo, branch, task["base"], task["head"], engine.item()["description"]))
        engine.advance()
    elif phase == "ci":
        candidate_gate(engine)
        if engine.github:
            task["ci_evidence"] = engine.github.checks(task["head"])
            if task["ci_evidence"].get("failed"):
                engine.hold("Trusted candidate CI failed; diagnose the check before retry/replan")
                return
            if not task["ci_evidence"]["passed"]:
                raise Unavailable("Waiting for exact candidate trusted checks")
            if any(row["kind"] == "ci" and "integration" in row["targets"] for row in criteria(engine.item())):
                pull = engine.github.pull(task["pr"]["number"])
                engine.github.identity(pull, task["base"], task["head"])
                if pull.get("mergeable") is not True or not pull.get("merge_commit_sha"):
                    raise Unavailable("Waiting for an exact integration merge")
                integration = engine.repo.fetch_merge(pull["merge_commit_sha"])
                require_merge_identity(task["base"], task["head"], engine.repo.parents(integration))
                task["integration_evidence"] = observe(engine, "integration", integration, external=True)
                if not task["integration_evidence"]["passed"] or not preserved(task, task["integration_evidence"]):
                    raise Closed("Integration snapshot verification failed")
        results, _ = observations(engine, task["candidate_evidence"], "integration")
        task["obligations"] = evaluate_obligations(criteria(engine.item()), results, stage="integration")
        if not task["obligations"]["passed"]:
            raise Closed("Integration-stage acceptance is incomplete")
        engine.advance()
    elif phase == "merge":
        # An uncertain remote merge must be reconciled before comparing a now-moved base.
        pending_merge = (engine.state.get("pending") or {}).get("kind") == "merge"
        if not pending_merge and not task.get("merge_sha"):
            candidate_gate(engine)
        critical = any(path_allowed(path, engine.policy["critical_paths"]) for path in engine.repo.changed(task["base"], task["head"]))
        authority = merge_authority(task["risk"], risk_ceiling=engine.goal["risk_ceiling"],
                                    auto_merge_ceiling=engine.goal["auto_merge_ceiling"], critical=critical)
        if authority["blocked"]:
            raise Closed("Hard risk ceiling cannot be approved")
        binding = fingerprint({"base": task["base"], "head": task["head"], "spec_hash": task["spec_hash"],
                               "risk": task["risk"], "policy_hash": engine.state["policy_hash"],
                               "runtime_hash": engine.state["runtime_hash"], "run_id": engine.state["run_id"]})
        if authority["requires_approval"] and task.get("approval") != binding:
            task["approval_required"] = binding
            engine.hold("Owner approval required for this exact candidate", kind="NEEDS_DECISION", approvable=True)
            return
        result = engine.store.effect("merge", {"base": task["base"], "head": task["head"], "approval": task.get("approval")},
            lambda identity: {"sha": engine.github.merge(task["pr"]["number"], task["base"], task["head"])
                if engine.github else engine.repo.merge_local(task["base"], task["head"], identity)})
        task["merge_sha"] = result["sha"]
        merged = engine.repo.fetch_merge(result["sha"]) if engine.github else result["sha"]
        require_merge_identity(task["base"], task["head"], engine.repo.parents(merged))
        task["merge_sha"] = merged
        engine.advance()
    elif phase == "postmerge":
        merged = task["merge_sha"]
        require_merge_identity(task["base"], task["head"], engine.repo.parents(merged))
        if engine.github:
            task["postmerge_checks"] = engine.github.checks(merged)
            if task["postmerge_checks"].get("failed"):
                engine.hold("Trusted merged-commit CI failed; completion remains blocked")
                return
            if not task["postmerge_checks"]["passed"]:
                raise Unavailable("Waiting for exact merged-commit trusted checks")
        receipt = observe(engine, phase, merged, external=True)
        if not receipt["passed"] or not preserved(task, receipt) or not frozen_intact(engine, merged):
            engine.hold("Merged commit failed independent verification; next item is blocked")
            return
        results, evidence = observations(engine, receipt, "postmerge")
        obligations = evaluate_obligations(criteria(engine.item()), results, stage="postmerge")
        if not obligations["complete"]:
            engine.hold("Post-merge acceptance is incomplete")
            return
        # Revalidate prior item evidence on this final product revision. Completion
        # of one item may not hide a later regression in an earlier item.
        for previous in engine.state["archive"]:
            if previous.get("phase") != "done":
                continue
            old_item = next(item for item in engine.goal["items"] if item["id"] == previous["id"])
            for edit in previous["frozen_tests"]["edits"]:
                if engine.repo.read(merged, edit["path"]) != edit["content"].encode():
                    raise Closed("Previously retained regression assertions changed")
            for criterion in criteria(old_item):
                if criterion["kind"] == "documentation" and not all(bool((engine.repo.read(merged, path) or b"").strip()) for path in criterion["paths"]):
                    raise Closed("Previously accepted documentation disappeared")
        task.update(postmerge_evidence=receipt, acceptance=evidence, obligations=obligations)
        engine.state["criteria"][task["id"]] = results
        engine.state["cli_cases"] = {key: row["passed"] for key, row in receipt["cli"].items()}
        engine.advance()
    elif phase == "done":
        result = completion_transition([row["id"] for row in engine.goal["items"]], engine.state["completed"], task["id"],
            merge_sha=task["merge_sha"], verification_passed=task["postmerge_evidence"]["passed"] and task["obligations"]["complete"])
        engine.state["completed"] = result["completed"]
        engine.state["archive"].append(task)
        engine.state.update(task=None, phase="reconcile", base=task["merge_sha"])
        if engine.state.pop("stop_after_merge", False):
            engine.state.update(status="CANCELLED", reason="Owner stopped the run after merged-effect verification")
    else:
        raise Closed("Unknown execution phase: " + phase)
