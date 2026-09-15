from __future__ import annotations

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
