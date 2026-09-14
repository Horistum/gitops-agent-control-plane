from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any


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
    return value


def require_fields(value: dict, required: set[str], *, where: str, allow_extra: bool = False) -> None:
    missing = required - set(value)
    extra = set(value) - required
    if missing or (extra and not allow_extra):
        raise ValueError(f"{where} fields invalid: missing={sorted(missing)} extra={sorted(extra)}")


def safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or path.as_posix() != value or "//" in value:
        raise ValueError(f"unsafe or non-canonical repository path: {value!r}")
    return value


def _glob_parts(path_parts: tuple[str, ...], pattern_parts: tuple[str, ...], i: int = 0, j: int = 0) -> bool:
    """Segment-aware glob. ** matches zero or more complete path segments."""
    while j < len(pattern_parts):
        token = pattern_parts[j]
        if token == "**":
            if j == len(pattern_parts) - 1:
                return True
            for next_i in range(i, len(path_parts) + 1):
                if _glob_parts(path_parts, pattern_parts, next_i, j + 1):
                    return True
            return False
        if i >= len(path_parts) or not fnmatch.fnmatchcase(path_parts[i], token):
            return False
        i += 1
        j += 1
    return i == len(path_parts)


def path_matches(path: str, pattern: str) -> bool:
    path = safe_relative_path(path)
    pattern_path = PurePosixPath(pattern)
    if pattern_path.is_absolute() or ".." in pattern_path.parts or pattern_path.as_posix() != pattern:
        raise ValueError(f"unsafe policy pattern: {pattern!r}")
    return _glob_parts(tuple(PurePosixPath(path).parts), tuple(pattern_path.parts))


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(path_matches(path, pattern) for pattern in patterns)


def matching_files(root: Path, patterns: list[str]) -> dict[str, str]:
    """Return stable path->sha256 map using exactly the same matcher as policy gates."""
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


def _validate_pattern(pattern: str) -> None:
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("policy pattern must be non-empty")
    p = PurePosixPath(pattern)
    if p.is_absolute() or ".." in p.parts or p.as_posix() != pattern:
        raise ValueError(f"unsafe policy pattern: {pattern!r}")


def validate_goal(goal: dict) -> None:
    required = {"schema", "objective", "items", "risk_ceiling", "auto_merge_ceiling", "success_condition", "forbidden_directions", "forbidden_paths"}
    require_fields(goal, required, where="goal")
    if goal["schema"] != 1:
        raise ValueError("goal schema must be 1")
    if not isinstance(goal["items"], list) or not goal["items"] or not all(isinstance(x, str) and x for x in goal["items"]):
        raise ValueError("goal.items must be a non-empty string list")
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


def validate_policy(policy: dict) -> None:
    required = {
        "schema", "reference_contract", "executor_mode", "developer_allowed_paths", "tester_allowed_paths",
        "authority_paths", "protected_test_paths", "risk_rules", "minimum_baseline_tests",
        "minimum_candidate_tests", "max_changed_files", "max_patch_bytes", "test_timeout_seconds",
        "default_risk", "human_gate_at",
    }
    require_fields(policy, required, where="policy")
    if policy["schema"] != 2 or policy["reference_contract"] != "gitops-agent-control-plane/v3":
        raise ValueError("unsupported policy contract")
    for key in ("developer_allowed_paths", "tester_allowed_paths", "authority_paths", "protected_test_paths"):
        if not isinstance(policy[key], list) or not all(isinstance(x, str) and x for x in policy[key]):
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
        for pattern in rule["paths"]:
            _validate_pattern(pattern)
    for key in ("minimum_baseline_tests", "minimum_candidate_tests", "max_changed_files", "max_patch_bytes", "test_timeout_seconds"):
        if type(policy[key]) is not int or policy[key] < 1:
            raise ValueError(f"policy.{key} must be positive integer")
