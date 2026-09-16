"""Strict supported JSON Schema vocabulary, independent of runtime profiles."""
from __future__ import annotations

import json
import math
import re
from typing import Any

__all__ = ["SchemaValidationError", "SUPPORTED_SCHEMA_KEYWORDS", "validate_instance", "validate_schema"]


class SchemaValidationError(ValueError):
    pass


SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema", "$id", "title", "description",
    "type", "const", "enum", "required", "properties", "additionalProperties",
    "minProperties", "maxProperties",
    "items", "minItems", "maxItems", "uniqueItems",
    "minLength", "maxLength", "pattern",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
}


def _type_ok(value: Any, expected: str) -> bool:
    mapping = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int or (type(value) is float and math.isfinite(value) and value.is_integer()),
        "number": type(value) is int or (type(value) is float and math.isfinite(value)),
        "boolean": type(value) is bool,
        "null": value is None,
    }
    if expected not in mapping:
        raise SchemaValidationError(f"unsupported JSON Schema type: {expected}")
    return mapping[expected]


def _json_key(value):
    """JSON equality: booleans differ from numbers; 1 and 1.0 are equal."""
    if value is None:
        return ("null",)
    if type(value) is bool:
        return ("boolean", value)
    if type(value) in (int, float):
        if type(value) is float and not math.isfinite(value):
            raise SchemaValidationError("Nonfinite values are not JSON numbers")
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(_json_key(v) for v in value))
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return ("object", tuple(sorted((k, _json_key(v)) for k, v in value.items())))
    raise SchemaValidationError("Value is not a JSON instance")


def validate_schema(schema: dict, path: str = "$schema") -> None:
    if not isinstance(schema, dict):
        raise SchemaValidationError(f"{path}: schema node must be an object")
    unknown = set(schema) - SUPPORTED_SCHEMA_KEYWORDS
    if unknown:
        raise SchemaValidationError(f"{path}: unsupported JSON Schema keywords {sorted(unknown)}")
    _json_key(schema)
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        valid = {"object", "array", "string", "integer", "number", "boolean", "null"}
        if not kinds or any(not isinstance(k, str) or k not in valid for k in kinds) or len(set(kinds)) != len(kinds):
            raise SchemaValidationError(f"{path}: invalid type declaration")
    for key in ("minProperties", "maxProperties", "minItems", "maxItems", "minLength", "maxLength"):
        if key in schema and (not _type_ok(schema[key], "integer") or schema[key] < 0):
            raise SchemaValidationError(f"{path}.{key}: expected nonnegative integer")
    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        if key in schema and not _type_ok(schema[key], "number"):
            raise SchemaValidationError(f"{path}.{key}: expected number")
    if "uniqueItems" in schema and type(schema["uniqueItems"]) is not bool:
        raise SchemaValidationError(f"{path}.uniqueItems: expected boolean")
    if "required" in schema:
        required = schema["required"]
        if (not isinstance(required, list) or any(not isinstance(k, str) for k in required)
                or len(set(required)) != len(required)):
            raise SchemaValidationError(f"{path}.required: expected unique strings")
    if "enum" in schema and not isinstance(schema["enum"], list):
        raise SchemaValidationError(f"{path}.enum: expected array")
    if "pattern" in schema:
        try:
            if not isinstance(schema["pattern"], str):
                raise TypeError("pattern must be a string")
            re.compile(schema["pattern"])
        except (TypeError, re.error) as exc:
            raise SchemaValidationError(f"{path}.pattern: invalid regex") from exc
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            raise SchemaValidationError(f"{path}.properties must be an object")
        for name, child in schema["properties"].items():
            validate_schema(child, f"{path}.properties[{name!r}]")
    if "items" in schema:
        if not isinstance(schema["items"], dict):
            raise SchemaValidationError(f"{path}.items: tuple/array schema forms are unsupported")
        validate_schema(schema["items"], f"{path}.items")
    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if type(additional) is bool:
            pass
        elif isinstance(additional, dict):
            validate_schema(additional, f"{path}.additionalProperties")
        else:
            raise SchemaValidationError(f"{path}.additionalProperties must be boolean or schema object")


def validate_instance(instance: Any, schema: dict, path: str = "$") -> None:
    # Direct callers get the same fail-closed keyword check as file callers.
    validate_schema(schema)
    _json_key(instance)
    _validate_instance(instance, schema, path)


def _validate_instance(instance: Any, schema: dict, path: str = "$") -> None:
    if "const" in schema and _json_key(instance) != _json_key(schema["const"]):
        raise SchemaValidationError(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and not any(_json_key(instance) == _json_key(v) for v in schema["enum"]):
        raise SchemaValidationError(f"{path}: {instance!r} not in enum")
    if "type" in schema:
        expected = schema["type"]
        if isinstance(expected, list):
            if not any(_type_ok(instance, item) for item in expected):
                raise SchemaValidationError(f"{path}: wrong type")
        elif not _type_ok(instance, expected):
            raise SchemaValidationError(f"{path}: expected {expected}")
    if isinstance(instance, dict):
        if len(instance) < schema.get("minProperties", 0):
            raise SchemaValidationError(f"{path}: too few properties")
        if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
            raise SchemaValidationError(f"{path}: too many properties")
        missing = [key for key in schema.get("required", []) if key not in instance]
        if missing:
            raise SchemaValidationError(f"{path}: missing required {missing}")
        props = schema.get("properties", {})
        extras = set(instance) - set(props)
        additional = schema.get("additionalProperties", True)
        if additional is False and extras:
            raise SchemaValidationError(f"{path}: unexpected properties {sorted(extras)}")
        for key, child in props.items():
            if key in instance:
                _validate_instance(instance[key], child, f"{path}.{key}")
        if isinstance(additional, dict):
            for key in extras:
                _validate_instance(instance[key], additional, f"{path}.{key}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise SchemaValidationError(f"{path}: too few items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise SchemaValidationError(f"{path}: too many items")
        if schema.get("uniqueItems"):
            serial = [_json_key(x) for x in instance]
            if len(set(serial)) != len(serial):
                raise SchemaValidationError(f"{path}: duplicate items")
        if "items" in schema:
            for i, value in enumerate(instance):
                _validate_instance(value, schema["items"], f"{path}[{i}]")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise SchemaValidationError(f"{path}: too short")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise SchemaValidationError(f"{path}: too long")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
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


