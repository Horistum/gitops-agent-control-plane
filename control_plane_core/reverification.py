"""Explicit bounded re-observation of completed verification, never model replay."""
from __future__ import annotations
import copy
from .execution import fingerprint
from .decisions import CoreError

PHASES = {"baseline", "verify", "independent_baseline", "independent_verify", "postmerge"}
MAX_REVERIFICATIONS = 3
AUTHORITY_FIELDS = (
    "id", "attempt", "head", "base", "spec_hash", "merge_sha", "goal_id", "goal_hash",
    "frozen_tests", "test_bindings", "tester_edits", "tester_overlay", "promoted_tests",
    "working_files", "working_set", "acceptance_map", "plan", "test_design", "scenarios",
    "risk", "critical_paths", "baseline_receipt", "baseline", "counterfactual_receipt",
    "independent_baseline", "independent_receipt", "test_receipt", "candidate_evidence",
    "workflow_contract", "item_revision", "proposed_tests", "production_head",
)


def authority(task, *, policy, goal, runtime):
    return {"policy": policy, "goal": goal, "runtime": runtime,
            "task": {key: copy.deepcopy(task.get(key)) for key in AUTHORITY_FIELDS},
            "reverifications": task.get("reverifications", 0)}


def failed_observation(current, phase, observation):
    if phase not in PHASES or not isinstance(observation, dict) or not observation:
        raise CoreError("Reverification requires a completed verification observation")
    return {"contract": "verification-recovery/v1", "authority": copy.deepcopy(current),
            "phase": phase, "observation": copy.deepcopy(observation),
            "observation_hash": fingerprint(observation)}


def binding(task, current):
    record = task.get("verification_recovery")
    count = task.get("reverifications", 0)
    if (task.get("phase") != "await_human" or task.get("pending") or task.get("approvable")
            or task.get("hold_kind") != "FAILED" or type(count) is not int
            or not 0 <= count < MAX_REVERIFICATIONS or not isinstance(record, dict)
            or record.get("contract") != "verification-recovery/v1" or record.get("phase") not in PHASES
            or record.get("phase") != task.get("resume_phase") or record.get("authority") != current
            or not isinstance(record.get("observation"), dict)
            or record.get("observation_hash") != fingerprint(record["observation"])):
        return None
    return fingerprint(record)


def resume(task, current, expected):
    observed = binding(task, current)
    if not expected or observed != expected:
        raise CoreError("Reverification binding is stale, unavailable or exhausted")
    record = copy.deepcopy(task["verification_recovery"])
    return {"phase": record["phase"], "reverifications": task.get("reverifications", 0) + 1,
            "record": record}
