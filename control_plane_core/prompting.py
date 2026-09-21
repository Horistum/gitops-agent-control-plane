"""Lossless prompt serialization; never an evidence or result cache."""
import copy
import json

__all__ = ["stable_prompt_json", "compact_prompt_schema"]


def stable_prompt_json(value, prefix=()):
    """Stable top-level ordering, canonical nested values, unchanged JSON meaning."""
    # Canonicalize nested maps too: insertion order is not prompt authority.
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if not isinstance(value, dict):
        return canonical
    ordered = json.loads(canonical)
    first = {key: ordered.pop(key) for key in prefix if key in ordered}
    first.update(ordered)
    return json.dumps(first, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def compact_prompt_schema(schema):
    """Omit only zero-length lower bounds already implied by JSON Schema types.

    The original schema remains the validator/structured-output authority.
    Literal values under enum/const/default are never traversed as schemas.
    """
    if not isinstance(schema, dict):
        return copy.deepcopy(schema)
    result = copy.deepcopy(schema)
    for keyword, kind in (("minLength", "string"), ("minItems", "array"), ("minProperties", "object")):
        if result.get("type") == kind and type(result.get(keyword)) is int and result[keyword] == 0:
            result.pop(keyword)
    for key in ("properties", "$defs", "definitions", "patternProperties"):
        if isinstance(result.get(key), dict):
            result[key] = {name: compact_prompt_schema(value) for name, value in result[key].items()}
    for key in ("items", "additionalProperties", "not", "if", "then", "else"):
        if isinstance(result.get(key), dict):
            result[key] = compact_prompt_schema(result[key])
    for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
        if isinstance(result.get(key), list):
            result[key] = [compact_prompt_schema(value) for value in result[key]]
    return result
