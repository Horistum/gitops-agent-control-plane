from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


class SchemaValidationError(ValueError):
    pass


SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema", "$id", "title", "description",
    "type", "const", "enum", "required", "properties", "additionalProperties",
    "items", "minItems", "maxItems", "uniqueItems",
    "minLength", "maxLength", "pattern",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
}


def _type_ok(value: Any, expected: str) -> bool:
    mapping = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "number": type(value) in (int, float),
        "boolean": type(value) is bool,
        "null": value is None,
    }
    if expected not in mapping:
        raise SchemaValidationError(f"unsupported JSON Schema type: {expected}")
    return mapping[expected]


def _validate_schema_definition(schema: dict, path: str = "$schema") -> None:
    if not isinstance(schema, dict):
        raise SchemaValidationError(f"{path}: schema node must be an object")
    unknown = set(schema) - SUPPORTED_SCHEMA_KEYWORDS
    if unknown:
        raise SchemaValidationError(f"{path}: unsupported JSON Schema keywords {sorted(unknown)}")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            raise SchemaValidationError(f"{path}.properties must be an object")
        for name, child in schema["properties"].items():
            _validate_schema_definition(child, f"{path}.properties[{name!r}]")
    if "items" in schema:
        if not isinstance(schema["items"], dict):
            raise SchemaValidationError(f"{path}.items: tuple/array schema forms are unsupported")
        _validate_schema_definition(schema["items"], f"{path}.items")
    if "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
        raise SchemaValidationError(f"{path}.additionalProperties: only boolean form is supported")


def validate_instance(instance: Any, schema: dict, path: str = "$") -> None:
    if "const" in schema and instance != schema["const"]:
        raise SchemaValidationError(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(f"{path}: {instance!r} not in enum")
    if "type" in schema:
        expected = schema["type"]
        if isinstance(expected, list):
            if not any(_type_ok(instance, item) for item in expected):
                raise SchemaValidationError(f"{path}: wrong type")
        elif not _type_ok(instance, expected):
            raise SchemaValidationError(f"{path}: expected {expected}")
    if isinstance(instance, dict):
        missing = [key for key in schema.get("required", []) if key not in instance]
        if missing:
            raise SchemaValidationError(f"{path}: missing required {missing}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(props)
            if extra:
                raise SchemaValidationError(f"{path}: unexpected properties {sorted(extra)}")
        for key, child in props.items():
            if key in instance:
                validate_instance(instance[key], child, f"{path}.{key}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise SchemaValidationError(f"{path}: too few items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise SchemaValidationError(f"{path}: too many items")
        if schema.get("uniqueItems"):
            serial = [json.dumps(x, sort_keys=True) for x in instance]
            if len(set(serial)) != len(serial):
                raise SchemaValidationError(f"{path}: duplicate items")
        if "items" in schema:
            for i, value in enumerate(instance):
                validate_instance(value, schema["items"], f"{path}[{i}]")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise SchemaValidationError(f"{path}: too short")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise SchemaValidationError(f"{path}: too long")
        if "pattern" in schema and re.fullmatch(schema["pattern"], instance) is None:
            raise SchemaValidationError(f"{path}: does not match pattern")
    if type(instance) in (int, float):
        if "minimum" in schema and instance < schema["minimum"]:
            raise SchemaValidationError(f"{path}: below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise SchemaValidationError(f"{path}: above maximum")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            raise SchemaValidationError(f"{path}: below/equal exclusiveMinimum")
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            raise SchemaValidationError(f"{path}: above/equal exclusiveMaximum")


def load_schema(path: Path) -> dict:
    value = json.loads(path.read_text())
    if value.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise SchemaValidationError(f"{path}: unexpected schema dialect")
    _validate_schema_definition(value, str(path))
    return value


def validate_json_file(instance_path: Path, schema_path: Path) -> None:
    validate_instance(json.loads(instance_path.read_text()), load_schema(schema_path))


def validate_jsonl_file(instance_path: Path, schema_path: Path) -> None:
    schema = load_schema(schema_path)
    for i, raw in enumerate(instance_path.read_text().splitlines(), 1):
        validate_instance(json.loads(raw), schema, f"$line[{i}]")


ARTIFACT_SCHEMAS = {
    "goal.json": "goal.schema.json",
    "policy.json": "policy.schema.json",
    "plan.json": "plan.schema.json",
    "state.json": "state.schema.json",
    "run-summary.json": "evidence.schema.json",
    "policy-decision.json": "policy-decision.schema.json",
    "review.json": "review.schema.json",
    "candidate-evidence.json": "candidate-evidence.schema.json",
    "merge-evidence.json": "merge-evidence.schema.json",
    "postmerge-evidence.json": "postmerge-evidence.schema.json",
    "recovery.json": "recovery.schema.json",
    "test-baseline.json": "test-evidence.schema.json",
    "test-candidate.json": "test-evidence.schema.json",
    "test-postmerge.json": "test-evidence.schema.json",
    "probe-baseline.json": "probe-evidence.schema.json",
    "probe-negative-control.json": "probe-evidence.schema.json",
    "probe-candidate.json": "probe-evidence.schema.json",
    "probe-postmerge.json": "probe-evidence.schema.json",
    "risk-decision.json": "risk-decision.schema.json",
}


def validate_evidence_directory(repository_root: Path, evidence: Path) -> list[str]:
    validated: list[str] = []
    for filename, schema_name in ARTIFACT_SCHEMAS.items():
        path = evidence / filename
        if path.is_file():
            validate_json_file(path, repository_root / "schemas" / schema_name)
            validated.append(filename)
    events = evidence / "events.jsonl"
    if events.is_file():
        validate_jsonl_file(events, repository_root / "schemas" / "event.schema.json")
        validated.append("events.jsonl")
    return validated
