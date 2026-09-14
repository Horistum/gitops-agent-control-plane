from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
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


def validate_goal(goal: dict) -> None:
    required = {"schema", "objective", "items", "risk_ceiling", "auto_merge_ceiling", "success_condition", "forbidden_directions"}
    require_fields(goal, required, where="goal")
    if goal["schema"] != 1:
        raise ValueError("goal schema must be 1")
    if not isinstance(goal["items"], list) or not goal["items"] or not all(isinstance(x, str) and x for x in goal["items"]):
        raise ValueError("goal.items must be a non-empty string list")
    if goal["risk_ceiling"] not in {"low", "medium", "high"}:
        raise ValueError("goal.risk_ceiling must be low, medium or high")
    if goal["auto_merge_ceiling"] not in {"none", "low", "medium"}:
        raise ValueError("goal.auto_merge_ceiling must be none, low or medium")
    for key in ("objective", "success_condition", "forbidden_directions"):
        if not isinstance(goal[key], str) or not goal[key].strip():
            raise ValueError(f"goal.{key} must be non-empty")


def validate_policy(policy: dict) -> None:
    required = {
        "schema", "reference_contract", "allowed_paths", "critical_paths", "authority_paths",
        "minimum_tests", "max_changed_files", "max_patch_bytes", "default_risk", "human_gate_at",
    }
    require_fields(policy, required, where="policy")
    if policy["schema"] != 1 or policy["reference_contract"] != "gitops-agent-control-plane/v2":
        raise ValueError("unsupported policy contract")
    for key in ("allowed_paths", "critical_paths", "authority_paths"):
        if not isinstance(policy[key], list) or not all(isinstance(x, str) and x for x in policy[key]):
            raise ValueError(f"policy.{key} must be a string list")
    if policy["default_risk"] not in {"low", "medium", "high"} or policy["human_gate_at"] not in {"medium", "high"}:
        raise ValueError("invalid risk policy")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def risk_rank(value: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}[value]


def digest_tree(root: Path, *, exclude_prefixes: tuple[str, ...] = (".git/", "build/", ".demo/")) -> str:
    rows: list[tuple[str, str]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        if any(relative == prefix.rstrip("/") or relative.startswith(prefix) for prefix in exclude_prefixes):
            continue
        rows.append((relative, sha256_bytes(path.read_bytes())))
    return sha256_json(rows)
