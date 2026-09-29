"""One authored schema per operational input and role; no fixture selectors."""
from __future__ import annotations

from pathlib import Path
import re
from control_plane_core import (acceptance_contract, goal_projection, risk_rank,
                                validate_goal_conditions, validate_predicates)
from control_plane_core.schema import validate_instance
from . import PROFILE
from .io import Closed


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def text(maximum=4000, minimum=0):
    return {"type": "string", "minLength": minimum, "maxLength": maximum}


def array(item, maximum=128, minimum=0):
    return {"type": "array", "items": item, "minItems": minimum, "maxItems": maximum}


def enum(*values):
    return {"type": "string", "enum": list(values)}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


RISK = enum("low", "medium", "high")
PATHS = array(text(500, 1))
# Keep legacy wire bounds; goal_projection validates ID syntax and graph integrity.
DEPENDENCY_IDS = array(text(500, 1))
ARGV = array(text(4000, 1), 64, 1)
EDIT = obj({"path": text(500, 1), "expected_sha256": text(64),
            "delete": {"type": "boolean"}, "content": text(1_000_000)})
BINDING = obj({"criterion_id": text(128, 1), "test_id": text(500, 1),
               "mode": enum("new_behavior", "regression")})
EVIDENCE = obj({"criterion_id": text(128, 1), "status": enum("covered", "deferred", "gap"),
                "evidence": text(4000, 1)})
COMMON = {"verdict": enum("ready", "fix", "replan", "blocked", "need_context"),
          "summary": text(4000, 1), "risk": RISK, "requested_files": PATHS,
          "requested_searches": array(text(200, 1), 8), "requested_facts": array(text(128, 1), 8),
          "findings": array(obj({"kind": enum("correctness", "architecture", "scope", "testing", "security", "evidence"),
                                  "severity": enum("low", "medium", "high", "critical"),
                                  "description": text(4000, 1)})),
          "acceptance_evidence": array(EVIDENCE)}
ROLE_SCHEMAS = {
    "discovery": obj({**COMMON, "selected_item": text(128)}),
    "architect": obj({**COMMON, "working_set": PATHS, "steps": array(text(2000, 1), 32)}),
    "test_design": obj({**COMMON, "scenarios": array(obj({"criterion_id": text(128, 1), "description": text(2000, 1)}))}),
    "developer": obj({**COMMON, "edits": array(EDIT, 32)}),
    "tester": obj({**COMMON, "edits": array(EDIT, 32), "bindings": array(BINDING, 256)}),
    **{name: obj(COMMON) for name in ("chief_plan", "reviewer", "challenge_review", "architect_accept", "chief_accept")},
}

PROVIDER_RESPONSE_SCHEMA = obj({
    "schema": {"type": "string", "const": "command-reasoning/v2"},
    "result": {"type": "object"},
    "usage": {"type": "object", "properties": {
        name: integer(0, 10**12) for name in ("input_tokens", "output_tokens", "cached_input_tokens")},
        "additionalProperties": False},
    "provider": obj({"id": text(200, 1), "model": text(200, 1), "request_id": text(500)})})


def normalize_role_output(value):
    # v1 command providers remain compatible; absence cannot grant a fact or
    # search. New structured providers receive the complete advertised schema.
    if isinstance(value, dict):
        value = {"requested_searches": [], "requested_facts": [], **value}
    return value
# Predicates and machine conditions are additionally validated by the portable core.
POLICY_SCHEMA = obj({
    "schema": {"type": "integer", "const": 1}, "profile": {"type": "string", "const": PROFILE},
    "product": text(4000, 1), "base_branch": text(128, 1),
    "allowed_paths": PATHS, "test_paths": PATHS, "protected_paths": PATHS, "critical_paths": PATHS,
    "risk_ceiling": RISK, "auto_merge_ceiling": enum("none", "low", "medium", "high"),
    "challenge": {"type": "boolean"},
    "limits": obj({"model_calls": integer(1, 256), "repairs": integer(0, 16),
                   "context_rounds": integer(1, 16), "context_files": integer(1, 128),
                   "context_bytes": integer(1000, 1_000_000), "edit_bytes": integer(1, 2_000_000)}),
    "reasoning": obj({"kind": enum("codex", "command"), "argv": ARGV, "model": text(200),
                       "codex_home": text(4000), "timeout": integer(1, 3600)}),
    "execution": obj({"kind": enum("podman", "trusted-local"), "image": text(1000),
                       "commands": array(ARGV, 32, 1), "junit": PATHS,
                       "min_tests": integer(1, 1_000_000), "timeout": integer(1, 7200),
                       "memory_mb": integer(128, 65536), "cpus": integer(1, 64),
                       "cases": array(obj({"id": text(128, 1), "argv": ARGV,
                           "predicates": array({"type": "object"}, 256, 1)}), 64)}),
    "publication": obj({"kind": enum("local", "github"), "repository": text(200),
                         "token_env": text(128), "required_checks": array(obj({"name": text(200, 1), "app_id": integer(1, 2**31)}), 32)}),
})
POLICY_SCHEMA["properties"]["adaptive_agent_graph"] = {"type": "boolean"}
CREDENTIAL_SCHEMA = {"type": "object", "properties": {
    "kind": enum("env", "command"), "name": text(128, 1), "argv": ARGV,
    "reference": text(1000, 1), "timeout": integer(1, 60)},
    "required": ["kind"], "additionalProperties": False}
# Optional additions preserve existing v1 policies. Cross-field constraints are
# enforced by validate_configuration and again at credential resolution.
POLICY_SCHEMA["properties"]["reasoning"]["properties"].update({
    "protocol": integer(1, 2),
    "check_argv": ARGV,
    "credentials": {"type": "object", "maxProperties": 16, "additionalProperties": CREDENTIAL_SCHEMA}})
from agent_worker.protocol import PROFILE_SCHEMA
POLICY_SCHEMA["properties"]["reasoning"]["properties"]["worker"] = PROFILE_SCHEMA
POLICY_SCHEMA["properties"]["publication"]["properties"]["credential"] = CREDENTIAL_SCHEMA
CRITERION = obj({"id": text(128, 1), "text": text(4000, 1),
                 "kind": enum("behavior", "compatibility", "documentation", "ci", "delivery"),
                 "paths": PATHS, "targets": array(enum("candidate", "integration"), 2)})
GOAL_SCHEMA = obj({"schema": {"type": "integer", "const": 1}, "id": text(128, 1),
                   "objective": text(4000, 1), "risk_ceiling": RISK,
                   "auto_merge_ceiling": enum("none", "low", "medium", "high"),
                   "items": array(obj({"id": text(128, 1), "dependencies": DEPENDENCY_IDS,
                                       "ready": {"type": "boolean"}, "risk": RISK,
                                       "description": text(8000, 1), "context": PATHS,
                                       "acceptance": array(CRITERION, 128, 1)}), 256, 1),
                   "machine_conditions": array({"type": "object"}, 256)})


def validate_configuration(policy, goal):
    validate_instance(policy, POLICY_SCHEMA)
    validate_instance(goal, GOAL_SCHEMA)
    from .credentials import validate_provider_credentials, validate_reference
    validate_provider_credentials(policy["reasoning"])
    if "worker" in policy["reasoning"]:
        from agent_worker.protocol import WorkerError, validate_profile
        if policy["reasoning"]["kind"] != "codex":
            raise Closed("Brokered app-server worker requires official Codex reasoning")
        try:
            validate_profile(policy["reasoning"]["worker"])
        except WorkerError as exc:
            raise Closed(str(exc)) from exc
    if policy["reasoning"]["kind"] != "command" and policy["reasoning"].get("protocol", 1) != 1:
        raise Closed("Versioned command protocol is only available for command reasoning")
    if policy["reasoning"]["kind"] != "command" and "check_argv" in policy["reasoning"]:
        raise Closed("Custom readiness handshake is only available for command reasoning")
    if "credential" in policy["publication"]:
        validate_reference(policy["publication"]["credential"])
        if policy["publication"]["kind"] != "github" or policy["publication"]["token_env"]:
            raise Closed("Use one GitHub credential source; set token_env to empty for a reference")
    if not Path(policy["product"]).is_absolute():
        raise Closed("Product checkout must be an absolute path")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", policy["base_branch"]):
        raise Closed("Invalid base branch")
    if risk_rank(goal["risk_ceiling"]) > risk_rank(policy["risk_ceiling"]):
        raise Closed("Goal exceeds operator risk authority")
    rank = lambda value: -1 if value == "none" else risk_rank(value)
    if rank(goal["auto_merge_ceiling"]) > rank(policy["auto_merge_ceiling"]):
        raise Closed("Goal exceeds operator merge authority")
    if not policy["allowed_paths"] or not policy["test_paths"] or not policy["execution"]["junit"]:
        raise Closed("Explicit source, test and JUnit envelopes required")
    if policy["execution"]["kind"] == "podman" and not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", policy["execution"]["image"]):
        raise Closed("Podman requires a locally available image pinned by digest")
    if policy["publication"]["kind"] == "github":
        pub = policy["publication"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", pub["repository"]) or not pub["required_checks"]:
            raise Closed("GitHub requires a repository identity and trusted named checks")
        if policy["execution"]["kind"] != "podman":
            raise Closed("GitHub publication requires isolated Podman execution")
        if "credential" not in pub and not re.fullmatch(r"[A-Z_][A-Z0-9_]*", pub["token_env"]):
            raise Closed("Invalid token environment variable")
    if policy["reasoning"]["kind"] == "codex" and not Path(policy["reasoning"]["codex_home"]).is_absolute():
        raise Closed("Codex requires an explicit absolute authenticated home")
    ids = [item["id"] for item in goal["items"]]
    goal_projection(ids, [], goal["items"])
    for item in goal["items"]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", item["id"]):
            raise Closed("Operational item IDs must be safe branch path components")
        if risk_rank(item["risk"]) > risk_rank(goal["risk_ceiling"]):
            raise Closed("Item exceeds goal risk authority")
        criteria(item)
        if policy["publication"]["kind"] == "local" and any(row["kind"] == "ci" for row in item["acceptance"]):
            raise Closed("CI obligations require a configured GitHub provider")
    cases = policy["execution"]["cases"]
    if len({case["id"] for case in cases}) != len(cases):
        raise Closed("CLI case identities must be unique")
    for case in cases:
        validate_predicates(case["predicates"])
    validate_goal_conditions(goal["machine_conditions"], ids, [case["id"] for case in cases])
    for condition in goal["machine_conditions"]:
        if condition["kind"] == "criterion":
            item = next(item for item in goal["items"] if item["id"] == condition["item"])
            if condition["criterion"] not in {row["id"] for row in item["acceptance"]}:
                raise Closed("Unknown goal acceptance criterion")


def criteria(item):
    return acceptance_contract([{"id": row["id"], "text": row["text"]} for row in item["acceptance"]],
                               [{"criterion_id": row["id"], "kind": row["kind"],
                                 "paths": row["paths"], "targets": row["targets"]} for row in item["acceptance"]])
