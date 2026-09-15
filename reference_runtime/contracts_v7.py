from __future__ import annotations

from copy import deepcopy

from . import _contracts_impl as _impl

ROLE_NAMES = {"discovery", "architect", "developer", "test-designer", "tester", "reviewer"}
AUTHORITY_CLASSES = {
    "intent_authority",
    "state_authority",
    "change_authority",
    "verification_authority",
    "context",
}
ROLE_WRITE_POLICY_REFS = {"none", "developer_allowed_paths", "tester_allowed_paths"}
MAX_ROADMAP_ITEMS = 256


def validate_role_protocols(value: dict) -> None:
    _impl.require_fields(value, {"schema", "roles"}, where="role_protocols")
    roles = value["roles"]
    if value["schema"] != 1 or not isinstance(roles, dict) or set(roles) != ROLE_NAMES:
        raise ValueError("role protocol surface invalid")
    for role, row in roles.items():
        if not isinstance(row, dict):
            raise ValueError(f"role protocol {role} must be an object")
        _impl.require_fields(
            row,
            {"inputs", "outputs", "product_write_power", "effect_power"},
            where=f"role_protocols.{role}",
        )
        if not isinstance(row["inputs"], list) or not row["inputs"] or not all(isinstance(item, str) and item for item in row["inputs"]):
            raise ValueError(f"role protocol {role} inputs invalid")
        if not isinstance(row["outputs"], list) or not row["outputs"] or not all(isinstance(item, str) and item for item in row["outputs"]):
            raise ValueError(f"role protocol {role} outputs invalid")
        write_ref = row["product_write_power"]
        if write_ref not in ROLE_WRITE_POLICY_REFS:
            raise ValueError(f"role protocol {role} references unsupported write authority {write_ref!r}")
        if role not in {"developer", "test-designer"} and write_ref != "none":
            raise ValueError(f"non-proposal role {role} cannot declare product write power")
        if row["effect_power"] != "none":
            raise ValueError(f"reasoning role {role} cannot declare effect power")


def validate_authority_model(model: dict) -> None:
    _impl.require_fields(model, {"schema", "classes", "artifacts"}, where="authority_model")
    if model["schema"] != 1:
        raise ValueError("authority-model schema must be 1")
    classes = model["classes"]
    if not isinstance(classes, dict) or set(classes) != AUTHORITY_CLASSES:
        raise ValueError("authority-model classes invalid")
    if not all(isinstance(value, str) and value for value in classes.values()):
        raise ValueError("authority-model class descriptions invalid")
    artifacts = model["artifacts"]
    required = {
        "authority-model.json",
        "roadmap.json",
        "release-state.json",
        "forbidden.json",
        "quality-gates.json",
        "verification-probes.json",
        "authority.md",
        "architecture.md",
    }
    if not isinstance(artifacts, dict):
        raise ValueError("authority-model artifacts invalid")
    missing = required - set(artifacts)
    if missing:
        raise ValueError(f"authority-model missing required artifacts: {sorted(missing)}")
    for name, row in artifacts.items():
        if not isinstance(row, dict):
            raise ValueError(f"authority-model artifact {name} must be an object")
        _impl.require_fields(row, {"class", "enforcement", "mutation"}, where=f"authority_model.{name}")
        if row["class"] not in AUTHORITY_CLASSES:
            raise ValueError(f"authority-model artifact {name} has unknown class")
        if row["enforcement"] not in {"machine", "reasoning-context"}:
            raise ValueError(f"authority-model artifact {name} has unsupported enforcement")
        if row["mutation"] not in {"product-owner", "controller-after-verified-effect"}:
            raise ValueError(f"authority-model artifact {name} has unsupported mutation authority")
        if row["class"] == "context" and row["enforcement"] != "reasoning-context":
            raise ValueError(f"context artifact {name} must be reasoning-context")
        if row["enforcement"] == "reasoning-context" and row["class"] != "context":
            raise ValueError(f"only context artifacts may use reasoning-context enforcement: {name}")
        if row["mutation"] == "controller-after-verified-effect" and (
            row["class"] != "state_authority" or row["enforcement"] != "machine"
        ):
            raise ValueError(f"controller-mutated artifact {name} must be machine state authority")


def role_write_policy_ref(protocols: dict, role: str) -> str:
    validate_role_protocols(protocols)
    if role not in protocols["roles"]:
        raise ValueError(f"unknown role protocol: {role}")
    return protocols["roles"][role]["product_write_power"]


def authority_artifact(model: dict, name: str) -> dict:
    validate_authority_model(model)
    try:
        return model["artifacts"][name]
    except KeyError as exc:
        raise ValueError(f"authority artifact not declared: {name}") from exc


def validate_goal(goal: dict) -> None:
    """Validate v7 goal semantics without pretending prose is executable policy."""
    expected_semantics = {
        "objective": "reasoning_context",
        "items": "enforced_intent",
        "risk_ceiling": "enforced_authority",
        "auto_merge_ceiling": "enforced_authority",
        "success_condition": "reasoning_context",
        "forbidden_directions": "reasoning_context",
        "forbidden_paths": "enforced_constraint",
        "autonomy": "enforced_authority",
    }
    if not isinstance(goal, dict) or goal.get("field_semantics") != expected_semantics:
        raise ValueError("goal.field_semantics must match actual v7 runtime semantics")

    # Reuse stable structural validation after translating only the legacy
    # semantic marker that v6 expected. The original object is never mutated.
    legacy = deepcopy(goal)
    legacy["field_semantics"] = dict(legacy["field_semantics"])
    legacy["field_semantics"]["success_condition"] = "verified_projection"
    _impl.validate_goal(legacy)


def validate_roadmap(roadmap: dict) -> None:
    items = roadmap.get("items") if isinstance(roadmap, dict) else None
    if isinstance(items, list) and len(items) > MAX_ROADMAP_ITEMS:
        raise ValueError(f"roadmap.items exceeds bounded limit {MAX_ROADMAP_ITEMS}")
    try:
        _impl.validate_roadmap(roadmap)
    except RecursionError as exc:
        raise ValueError("roadmap dependency graph exceeds supported validation depth") from exc

    # Repeat the cycle proof iteratively so the public v7 contract does not
    # rely on recursive DFS semantics. With the explicit item limit this is
    # bounded O(V + E) owner-authored work.
    ids = [item["id"] for item in roadmap["items"]]
    by_id = {item["id"]: item for item in roadmap["items"]}
    indegree = {item_id: len(by_id[item_id]["dependencies"]) for item_id in ids}
    dependents = {item_id: [] for item_id in ids}
    for item_id in ids:
        for dependency in by_id[item_id]["dependencies"]:
            dependents[dependency].append(item_id)
    ready = [item_id for item_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    if visited != len(ids):
        cyclic = sorted(item_id for item_id, degree in indegree.items() if degree > 0)
        raise ValueError(f"roadmap dependency cycle detected: {cyclic}")


def validate_goal_against_roadmap(goal: dict, roadmap: dict) -> None:
    validate_goal(goal)
    validate_roadmap(roadmap)
    known = {item["id"] for item in roadmap["items"]}
    unknown = set(goal["items"]) - known
    if unknown:
        raise ValueError(f"goal requests unknown roadmap items: {sorted(unknown)}")
