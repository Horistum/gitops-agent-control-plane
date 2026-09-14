from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any


REFERENCE_CONTRACT = "gitops-agent-control-plane/v7"
CORE_CONTRACT = "autonomous-control-plane/v1"
VERIFICATION_PROFILE = "property-probe/v6"
RUNTIME_PROFILE = "standalone-local/v2"


ROLE_NAMES = {"discovery", "architect", "developer", "test-designer", "tester", "reviewer"}
AUTHORITY_CLASSES = {
    "intent_authority",
    "state_authority",
    "change_authority",
    "verification_authority",
    "context",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode())


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")

    # Authority/config validation is deliberately attached to the common loader,
    # so fresh runs and resumed runs fail closed even outside repository CI.
    if path.name == "roadmap.json":
        validate_roadmap(value)
    elif path.name == "release-state.json":
        roadmap_path = path.with_name("roadmap.json")
        roadmap = json.loads(roadmap_path.read_text()) if roadmap_path.is_file() else None
        if roadmap is not None:
            validate_roadmap(roadmap)
        validate_release_state(value, roadmap)
    elif path.name == "authority-model.json":
        validate_authority_model(value)
    elif path.name == "role-protocols.json":
        validate_role_protocols(value)
    return value


def require_fields(value: dict, required: set[str], *, where: str, optional: set[str] | None = None) -> None:
    optional = optional or set()
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing or extra:
        raise ValueError(f"{where} fields invalid: missing={sorted(missing)} extra={sorted(extra)}")


def safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or path.as_posix() != value or "//" in value:
        raise ValueError(f"unsafe or non-canonical repository path: {value!r}")
    return value


def _validate_pattern(pattern: str) -> None:
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("policy pattern must be non-empty")
    p = PurePosixPath(pattern)
    if p.is_absolute() or ".." in p.parts or p.as_posix() != pattern or "//" in pattern:
        raise ValueError(f"unsafe policy pattern: {pattern!r}")


def path_matches(path: str, pattern: str) -> bool:
    """Segment-aware glob with memoized `**` matching.

    `**` matches zero or more complete path segments. Memoizing
    `(path_index, pattern_index)` bounds matching to O(P*L) states and avoids
    exponential backtracking from repeated owner-authored `**` tokens.
    """
    path = safe_relative_path(path)
    _validate_pattern(pattern)
    path_parts = tuple(PurePosixPath(path).parts)
    raw = tuple(PurePosixPath(pattern).parts)
    pattern_parts = tuple(part for i, part in enumerate(raw) if part != "**" or i == 0 or raw[i - 1] != "**")

    @lru_cache(maxsize=None)
    def match(i: int, j: int) -> bool:
        if j == len(pattern_parts):
            return i == len(path_parts)
        token = pattern_parts[j]
        if token == "**":
            return match(i, j + 1) or (i < len(path_parts) and match(i + 1, j))
        return i < len(path_parts) and fnmatch.fnmatchcase(path_parts[i], token) and match(i + 1, j + 1)

    return match(0, 0)


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(path_matches(path, pattern) for pattern in patterns)


def matching_files(root: Path, patterns: list[str]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for candidate in sorted(root.rglob("*")):
        if not candidate.is_file() or candidate.is_symlink():
            continue
        relative = candidate.relative_to(root).as_posix()
        if matches_any(relative, patterns):
            rows[relative] = sha256_bytes(candidate.read_bytes())
    return rows


def digest_paths(root: Path, patterns: list[str]) -> dict:
    files = matching_files(root, patterns)
    return {"schema": 1, "files": files, "digest": sha256_json(files)}


def digest_tree(root: Path, *, exclude_patterns: tuple[str, ...] = (".git/**", "build/**", ".demo/**", "**/__pycache__/**", "**/*.pyc", "**/*.pyo")) -> str:
    rows: list[tuple[str, str]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
        relative = path.relative_to(root).as_posix()
        if matches_any(relative, list(exclude_patterns)):
            continue
        rows.append((relative, sha256_bytes(path.read_bytes())))
    return sha256_json(rows)


def risk_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}[value]


def validate_contract_set(value: dict) -> None:
    require_fields(value, {"schema", "reference_contract", "core_contract", "verification_profile", "runtime_profile"}, where="contract_set")
    if value != {"schema": 1, "reference_contract": REFERENCE_CONTRACT, "core_contract": CORE_CONTRACT, "verification_profile": VERIFICATION_PROFILE, "runtime_profile": RUNTIME_PROFILE}:
        raise ValueError("unsupported contract set")


def validate_goal(goal: dict) -> None:
    required = {"schema", "objective", "items", "risk_ceiling", "auto_merge_ceiling", "success_condition", "forbidden_directions", "forbidden_paths", "autonomy", "field_semantics"}
    require_fields(goal, required, where="goal")
    if goal["schema"] != 2:
        raise ValueError("goal schema must be 2")
    if not isinstance(goal["items"], list) or not goal["items"] or not all(isinstance(x, str) and x for x in goal["items"]):
        raise ValueError("goal.items must be a non-empty string list")
    if len(goal["items"]) != len(set(goal["items"])):
        raise ValueError("goal.items must be unique")
    if goal["risk_ceiling"] not in {"low", "medium", "high"}:
        raise ValueError("invalid risk_ceiling")
    if goal["auto_merge_ceiling"] not in {"none", "low", "medium"}:
        raise ValueError("invalid auto_merge_ceiling")
    if not isinstance(goal["forbidden_paths"], list) or not all(isinstance(x, str) and x for x in goal["forbidden_paths"]):
        raise ValueError("goal.forbidden_paths must be a string list")
    for pattern in goal["forbidden_paths"]:
        _validate_pattern(pattern)
    for key in ("objective", "success_condition", "forbidden_directions"):
        if not isinstance(goal[key], str) or not goal[key].strip():
            raise ValueError(f"goal.{key} must be non-empty")
    autonomy = goal["autonomy"]
    require_fields(autonomy, {"max_cycles", "max_attempts_per_item"}, where="goal.autonomy")
    for key in ("max_cycles", "max_attempts_per_item"):
        if type(autonomy[key]) is not int or autonomy[key] < 1:
            raise ValueError(f"goal.autonomy.{key} must be positive integer")
    expected = {
        "objective": "reasoning_context",
        "items": "enforced_intent",
        "risk_ceiling": "enforced_authority",
        "auto_merge_ceiling": "enforced_authority",
        "success_condition": "verified_projection",
        "forbidden_directions": "reasoning_context",
        "forbidden_paths": "enforced_constraint",
        "autonomy": "enforced_authority",
    }
    if goal["field_semantics"] != expected:
        raise ValueError("goal.field_semantics must explicitly classify every goal field")


def validate_policy(policy: dict) -> None:
    required = {"schema", "reference_contract", "contracts", "executor_mode", "developer_allowed_paths", "tester_allowed_paths", "authority_paths", "protected_test_paths", "risk_rules", "minimum_baseline_tests", "max_changed_files", "max_patch_bytes", "test_timeout_seconds", "default_risk", "human_gate_at", "max_cycles", "max_attempts_per_item"}
    require_fields(policy, required, where="policy")
    if policy["schema"] != 6 or policy["reference_contract"] != REFERENCE_CONTRACT:
        raise ValueError("unsupported policy contract")
    if policy["contracts"] != {"core": CORE_CONTRACT, "verification": VERIFICATION_PROFILE, "runtime": RUNTIME_PROFILE}:
        raise ValueError("policy contract profiles mismatch")
    for key in ("developer_allowed_paths", "tester_allowed_paths", "authority_paths", "protected_test_paths"):
        if not isinstance(policy[key], list) or not policy[key] or not all(isinstance(x, str) and x for x in policy[key]):
            raise ValueError(f"policy.{key} must be a non-empty string list")
        for pattern in policy[key]:
            _validate_pattern(pattern)
    if policy["executor_mode"] != "trusted-fixture-local":
        raise ValueError("standalone reference only supports trusted-fixture-local executor")
    if policy["default_risk"] not in {"low", "medium", "high"} or policy["human_gate_at"] not in {"medium", "high"}:
        raise ValueError("invalid risk policy")
    if not isinstance(policy["risk_rules"], list):
        raise ValueError("risk_rules must be a list")
    for rule in policy["risk_rules"]:
        require_fields(rule, {"risk", "paths"}, where="risk_rule")
        if rule["risk"] not in {"medium", "high"}:
            raise ValueError("risk rule must be medium/high")
        if not isinstance(rule["paths"], list) or not rule["paths"]:
            raise ValueError("risk rule paths must be a non-empty list")
        for pattern in rule["paths"]:
            _validate_pattern(pattern)
    for key in ("minimum_baseline_tests", "max_changed_files", "max_patch_bytes", "test_timeout_seconds", "max_cycles", "max_attempts_per_item"):
        if type(policy[key]) is not int or policy[key] < 1:
            raise ValueError(f"policy.{key} must be positive integer")


def validate_roadmap(roadmap: dict) -> None:
    require_fields(roadmap, {"schema", "items"}, where="roadmap")
    if roadmap["schema"] != 4:
        raise ValueError("roadmap schema must be 4")
    items = roadmap["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("roadmap.items must be a non-empty list")

    ids: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"roadmap.items[{index}] must be an object")
        require_fields(item, {"id", "title", "status", "dependencies", "goal", "acceptance", "non_goals"}, where=f"roadmap.items[{index}]")
        item_id = item["id"]
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("roadmap item id must be non-empty")
        ids.append(item_id)
        if item["status"] not in {"ready", "planned", "blocked"}:
            raise ValueError(f"roadmap item {item_id} has unsupported status")
        if not isinstance(item["title"], str) or not item["title"].strip() or not isinstance(item["goal"], str) or not item["goal"].strip():
            raise ValueError(f"roadmap item {item_id} title/goal invalid")
        dependencies = item["dependencies"]
        if not isinstance(dependencies, list) or not all(isinstance(dep, str) and dep for dep in dependencies):
            raise ValueError(f"roadmap item {item_id} dependencies invalid")
        if len(dependencies) != len(set(dependencies)) or item_id in dependencies:
            raise ValueError(f"roadmap item {item_id} has duplicate/self dependency")
        acceptance = item["acceptance"]
        if not isinstance(acceptance, list) or not acceptance:
            raise ValueError(f"roadmap item {item_id} acceptance must be non-empty")
        criterion_ids: list[str] = []
        for criterion in acceptance:
            if not isinstance(criterion, dict):
                raise ValueError(f"roadmap item {item_id} acceptance criterion invalid")
            require_fields(criterion, {"id", "text", "probe_ids"}, where=f"roadmap item {item_id} acceptance")
            criterion_ids.append(criterion["id"])
            if not isinstance(criterion["id"], str) or not criterion["id"] or not isinstance(criterion["text"], str) or not criterion["text"].strip():
                raise ValueError(f"roadmap item {item_id} acceptance identity/text invalid")
            probes = criterion["probe_ids"]
            if not isinstance(probes, list) or not probes or not all(isinstance(probe, str) and probe for probe in probes) or len(probes) != len(set(probes)):
                raise ValueError(f"roadmap item {item_id} acceptance probe_ids invalid")
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError(f"roadmap item {item_id} acceptance ids must be unique")
        if not isinstance(item["non_goals"], list) or not all(isinstance(value, str) and value for value in item["non_goals"]):
            raise ValueError(f"roadmap item {item_id} non_goals invalid")

    if len(ids) != len(set(ids)):
        raise ValueError("roadmap item ids must be unique")
    known = set(ids)
    by_id = {item["id"]: item for item in items}
    for item in items:
        unknown = set(item["dependencies"]) - known
        if unknown:
            raise ValueError(f"roadmap item {item['id']} references unknown dependencies: {sorted(unknown)}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str) -> None:
        if item_id in visiting:
            raise ValueError(f"roadmap dependency cycle detected at {item_id}")
        if item_id in visited:
            return
        visiting.add(item_id)
        for dependency in by_id[item_id]["dependencies"]:
            visit(dependency)
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in ids:
        visit(item_id)


def validate_release_state(state: dict, roadmap: dict | None = None) -> None:
    require_fields(state, {"schema", "completed", "history", "notes"}, where="release_state")
    if state["schema"] != 2:
        raise ValueError("release-state schema must be 2")
    completed = state["completed"]
    if not isinstance(completed, list) or not all(isinstance(item, str) and item for item in completed) or len(completed) != len(set(completed)):
        raise ValueError("release-state completed must be a unique string list")
    history = state["history"]
    if not isinstance(history, list):
        raise ValueError("release-state history must be a list")
    history_ids: list[str] = []
    for row in history:
        if not isinstance(row, dict):
            raise ValueError("release-state history entry must be an object")
        require_fields(row, {"item", "verified_merge_sha", "recorded_by"}, where="release_state.history")
        if row["recorded_by"] != "controller":
            raise ValueError("release-state history must be controller recorded")
        if not isinstance(row["item"], str) or not row["item"]:
            raise ValueError("release-state history item invalid")
        if not isinstance(row["verified_merge_sha"], str) or re.fullmatch(r"[0-9a-f]{40}", row["verified_merge_sha"]) is None:
            raise ValueError("release-state verified_merge_sha invalid")
        history_ids.append(row["item"])
    if history_ids != completed:
        raise ValueError("release-state history order must exactly match completed items")
    if not isinstance(state["notes"], list) or not all(isinstance(note, str) for note in state["notes"]):
        raise ValueError("release-state notes must be strings")

    if roadmap is not None:
        known = {item["id"] for item in roadmap["items"]}
        unknown = set(completed) - known
        if unknown:
            raise ValueError(f"release-state contains unknown completed items: {sorted(unknown)}")
        seen: set[str] = set()
        by_id = {item["id"]: item for item in roadmap["items"]}
        for item_id in completed:
            missing = set(by_id[item_id]["dependencies"]) - seen
            if missing:
                raise ValueError(f"release-state completed {item_id} before dependencies: {sorted(missing)}")
            seen.add(item_id)


def validate_goal_against_roadmap(goal: dict, roadmap: dict) -> None:
    validate_goal(goal)
    validate_roadmap(roadmap)
    known = {item["id"] for item in roadmap["items"]}
    unknown = set(goal["items"]) - known
    if unknown:
        raise ValueError(f"goal requests unknown roadmap items: {sorted(unknown)}")


def validate_authority_model(model: dict) -> None:
    require_fields(model, {"schema", "classes", "artifacts"}, where="authority_model")
    if model["schema"] != 1:
        raise ValueError("authority-model schema must be 1")
    if not isinstance(model["classes"], dict) or set(model["classes"]) != AUTHORITY_CLASSES:
        raise ValueError("authority-model classes invalid")
    if not all(isinstance(value, str) and value for value in model["classes"].values()):
        raise ValueError("authority-model class descriptions invalid")
    required_artifacts = {
        "roadmap.json": ("intent_authority", "machine", "product-owner"),
        "release-state.json": ("state_authority", "machine", "controller-after-verified-effect"),
        "forbidden.json": ("change_authority", "machine", "product-owner"),
        "quality-gates.json": ("verification_authority", "machine", "product-owner"),
        "verification-probes.json": ("verification_authority", "machine", "product-owner"),
        "authority.md": ("context", "reasoning-context", "product-owner"),
        "architecture.md": ("context", "reasoning-context", "product-owner"),
    }
    if not isinstance(model["artifacts"], dict) or set(model["artifacts"]) != set(required_artifacts):
        raise ValueError("authority-model artifacts invalid")
    for name, expected in required_artifacts.items():
        row = model["artifacts"][name]
        require_fields(row, {"class", "enforcement", "mutation"}, where=f"authority_model.{name}")
        observed = (row["class"], row["enforcement"], row["mutation"])
        if observed != expected:
            raise ValueError(f"authority-model semantics invalid for {name}: {observed}")


def validate_role_protocols(value: dict) -> None:
    require_fields(value, {"schema", "roles"}, where="role_protocols")
    if value["schema"] != 1 or not isinstance(value["roles"], dict) or set(value["roles"]) != ROLE_NAMES:
        raise ValueError("role protocol surface invalid")
    expected_write = {
        "discovery": "none",
        "architect": "none",
        "developer": "developer_allowed_paths",
        "test-designer": "tester_allowed_paths",
        "tester": "none",
        "reviewer": "none",
    }
    for role, row in value["roles"].items():
        if not isinstance(row, dict):
            raise ValueError(f"role protocol {role} must be an object")
        require_fields(row, {"inputs", "outputs", "product_write_power", "effect_power"}, where=f"role_protocols.{role}")
        if not isinstance(row["inputs"], list) or not row["inputs"] or not all(isinstance(item, str) and item for item in row["inputs"]):
            raise ValueError(f"role protocol {role} inputs invalid")
        if not isinstance(row["outputs"], list) or not row["outputs"] or not all(isinstance(item, str) and item for item in row["outputs"]):
            raise ValueError(f"role protocol {role} outputs invalid")
        if row["product_write_power"] != expected_write[role]:
            raise ValueError(f"role protocol {role} write power invalid")
        if row["effect_power"] != "none":
            raise ValueError(f"role protocol {role} gained effect power")
