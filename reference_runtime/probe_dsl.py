from __future__ import annotations

import secrets
import string
from typing import Any


class ProbeContractError(ValueError):
    pass


SUPPORTED_EXCEPTIONS = {
    "AssertionError",
    "IndexError",
    "KeyError",
    "TypeError",
    "ValueError",
    "ZeroDivisionError",
}
SUPPORTED_GENERATORS = {
    "boolean",
    "choice",
    "constant",
    "integer",
    "null",
    "text-tokens",
    "whitespace",
}
SUPPORTED_EXPR_OPS = {
    "arg",
    "concat",
    "join",
    "kwarg",
    "length",
    "literal",
    "lower",
    "split-whitespace",
    "strip",
    "upper",
}


def _exact_keys(value: dict, required: set[str], optional: set[str] = set(), *, where: str) -> None:
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing or extra:
        raise ProbeContractError(f"{where} fields invalid: missing={sorted(missing)} extra={sorted(extra)}")


def _positive_int(value: Any, *, where: str, maximum: int | None = None) -> int:
    if type(value) is not int or value < 1 or (maximum is not None and value > maximum):
        raise ProbeContractError(f"{where} must be an integer in range 1..{maximum or 'unbounded'}")
    return value


def _validate_range(value: dict, *, where: str, minimum_floor: int = 0, maximum_ceiling: int = 128) -> None:
    _exact_keys(value, {"min", "max"}, where=where)
    low, high = value["min"], value["max"]
    if type(low) is not int or type(high) is not int or low < minimum_floor or high < low or high > maximum_ceiling:
        raise ProbeContractError(f"{where} range invalid")


def validate_generator(spec: dict, *, where: str = "generator") -> None:
    if not isinstance(spec, dict) or not isinstance(spec.get("kind"), str):
        raise ProbeContractError(f"{where} must be an object with kind")
    kind = spec["kind"]
    if kind not in SUPPORTED_GENERATORS:
        raise ProbeContractError(f"{where} unsupported generator: {kind}")
    if kind == "constant":
        _exact_keys(spec, {"kind", "value"}, where=where)
    elif kind in {"boolean", "null"}:
        _exact_keys(spec, {"kind"}, where=where)
    elif kind == "integer":
        _exact_keys(spec, {"kind", "min", "max"}, where=where)
        if type(spec["min"]) is not int or type(spec["max"]) is not int or spec["max"] < spec["min"]:
            raise ProbeContractError(f"{where} integer range invalid")
    elif kind == "choice":
        _exact_keys(spec, {"kind", "options"}, where=where)
        options = spec["options"]
        if not isinstance(options, list) or not options:
            raise ProbeContractError(f"{where}.options must be non-empty")
        for i, option in enumerate(options):
            validate_generator(option, where=f"{where}.options[{i}]")
    elif kind == "whitespace":
        _exact_keys(spec, {"kind", "characters", "length"}, where=where)
        chars = spec["characters"]
        if not isinstance(chars, str) or not chars or any(not ch.isspace() for ch in chars):
            raise ProbeContractError(f"{where}.characters must contain whitespace only")
        _validate_range(spec["length"], where=f"{where}.length", minimum_floor=1)
    elif kind == "text-tokens":
        _exact_keys(
            spec,
            {"kind", "alphabet", "token_count", "token_length", "separators", "prefixes", "suffixes"},
            where=where,
        )
        if not isinstance(spec["alphabet"], str) or len(set(spec["alphabet"])) < 2 or any(ch.isspace() for ch in spec["alphabet"]):
            raise ProbeContractError(f"{where}.alphabet must contain at least two non-whitespace characters")
        _validate_range(spec["token_count"], where=f"{where}.token_count", minimum_floor=1, maximum_ceiling=12)
        _validate_range(spec["token_length"], where=f"{where}.token_length", minimum_floor=1, maximum_ceiling=32)
        for key in ("separators", "prefixes", "suffixes"):
            values = spec[key]
            if not isinstance(values, list) or not values or not all(isinstance(x, str) for x in values):
                raise ProbeContractError(f"{where}.{key} must be a non-empty string list")
        if any(not value or not all(ch.isspace() for ch in value) for value in spec["separators"]):
            raise ProbeContractError(f"{where}.separators must contain non-empty whitespace strings")
        if any(not all(ch.isspace() for ch in value) for value in spec["prefixes"] + spec["suffixes"]):
            raise ProbeContractError(f"{where} prefixes/suffixes must contain whitespace only")


def validate_expression(expr: dict, *, where: str = "expression") -> None:
    if not isinstance(expr, dict) or not isinstance(expr.get("op"), str):
        raise ProbeContractError(f"{where} must be an object with op")
    op = expr["op"]
    if op not in SUPPORTED_EXPR_OPS:
        raise ProbeContractError(f"{where} unsupported expression op: {op}")
    if op == "literal":
        _exact_keys(expr, {"op", "value"}, where=where)
    elif op == "arg":
        _exact_keys(expr, {"op", "index"}, where=where)
        if type(expr["index"]) is not int or expr["index"] < 0:
            raise ProbeContractError(f"{where}.index must be non-negative integer")
    elif op == "kwarg":
        _exact_keys(expr, {"op", "name"}, where=where)
        if not isinstance(expr["name"], str) or not expr["name"]:
            raise ProbeContractError(f"{where}.name must be non-empty")
    elif op == "concat":
        _exact_keys(expr, {"op", "parts"}, where=where)
        if not isinstance(expr["parts"], list) or not expr["parts"]:
            raise ProbeContractError(f"{where}.parts must be non-empty")
        for i, part in enumerate(expr["parts"]):
            validate_expression(part, where=f"{where}.parts[{i}]")
    elif op == "join":
        _exact_keys(expr, {"op", "separator", "items"}, where=where)
        if not isinstance(expr["separator"], str):
            raise ProbeContractError(f"{where}.separator must be string")
        validate_expression(expr["items"], where=f"{where}.items")
    elif op in {"split-whitespace", "lower", "upper", "strip", "length"}:
        _exact_keys(expr, {"op", "value"}, where=where)
        validate_expression(expr["value"], where=f"{where}.value")


def validate_probe(probe: dict) -> None:
    if not isinstance(probe, dict):
        raise ProbeContractError("probe must be object")
    _exact_keys(probe, {"id", "target", "callable", "cases", "oracle"}, where="probe")
    if not isinstance(probe["id"], str) or not probe["id"]:
        raise ProbeContractError("probe.id must be non-empty string")
    if not isinstance(probe["target"], str) or not probe["target"]:
        raise ProbeContractError("probe.target must be non-empty string")
    if not isinstance(probe["callable"], str) or not probe["callable"]:
        raise ProbeContractError("probe.callable must be non-empty string")

    cases = probe["cases"]
    if not isinstance(cases, dict):
        raise ProbeContractError("probe.cases must be object")
    _exact_keys(cases, {"count", "args", "kwargs"}, where="probe.cases")
    _positive_int(cases["count"], where="probe.cases.count", maximum=32)
    if not isinstance(cases["args"], list):
        raise ProbeContractError("probe.cases.args must be array")
    for i, generator in enumerate(cases["args"]):
        validate_generator(generator, where=f"probe.cases.args[{i}]")
    if not isinstance(cases["kwargs"], list):
        raise ProbeContractError("probe.cases.kwargs must be array")
    names: list[str] = []
    for i, binding in enumerate(cases["kwargs"]):
        if not isinstance(binding, dict):
            raise ProbeContractError(f"probe.cases.kwargs[{i}] must be object")
        _exact_keys(binding, {"name", "generator"}, where=f"probe.cases.kwargs[{i}]")
        if not isinstance(binding["name"], str) or not binding["name"]:
            raise ProbeContractError(f"probe.cases.kwargs[{i}].name invalid")
        names.append(binding["name"])
        validate_generator(binding["generator"], where=f"probe.cases.kwargs[{i}].generator")
    if len(names) != len(set(names)):
        raise ProbeContractError("probe.cases.kwargs names must be unique")

    oracle = probe["oracle"]
    if not isinstance(oracle, dict) or not isinstance(oracle.get("kind"), str):
        raise ProbeContractError("probe.oracle must be object with kind")
    if oracle["kind"] == "raises":
        _exact_keys(oracle, {"kind", "exception"}, where="probe.oracle")
        if oracle["exception"] not in SUPPORTED_EXCEPTIONS:
            raise ProbeContractError(f"unsupported exception oracle: {oracle['exception']}")
    elif oracle["kind"] == "return-equals":
        _exact_keys(oracle, {"kind", "expected"}, where="probe.oracle")
        validate_expression(oracle["expected"], where="probe.oracle.expected")
    else:
        raise ProbeContractError(f"unsupported oracle kind: {oracle['kind']}")


def _rand_range(spec: dict) -> int:
    return spec["min"] + secrets.randbelow(spec["max"] - spec["min"] + 1)


def generate_value(spec: dict) -> Any:
    kind = spec["kind"]
    if kind == "constant":
        return spec["value"]
    if kind == "null":
        return None
    if kind == "boolean":
        return bool(secrets.randbelow(2))
    if kind == "integer":
        return spec["min"] + secrets.randbelow(spec["max"] - spec["min"] + 1)
    if kind == "choice":
        return generate_value(secrets.choice(spec["options"]))
    if kind == "whitespace":
        return "".join(secrets.choice(spec["characters"]) for _ in range(_rand_range(spec["length"])))
    if kind == "text-tokens":
        tokens = []
        for _ in range(_rand_range(spec["token_count"])):
            tokens.append("".join(secrets.choice(spec["alphabet"]) for _ in range(_rand_range(spec["token_length"]))))
        return secrets.choice(spec["prefixes"]) + secrets.choice(spec["separators"]).join(tokens) + secrets.choice(spec["suffixes"])
    raise ProbeContractError(f"unsupported generator at runtime: {kind}")


def materialize_cases(probe: dict) -> list[dict]:
    cases = probe["cases"]
    rows: list[dict] = []
    for index in range(cases["count"]):
        args = [generate_value(generator) for generator in cases["args"]]
        kwargs = {binding["name"]: generate_value(binding["generator"]) for binding in cases["kwargs"]}
        rows.append({"case": index + 1, "args": args, "kwargs": kwargs})
    return rows


def evaluate_expression(expr: dict, args: list, kwargs: dict) -> Any:
    op = expr["op"]
    if op == "literal":
        return expr["value"]
    if op == "arg":
        return args[expr["index"]]
    if op == "kwarg":
        return kwargs[expr["name"]]
    if op == "concat":
        return "".join(str(evaluate_expression(part, args, kwargs)) for part in expr["parts"])
    if op == "split-whitespace":
        return str(evaluate_expression(expr["value"], args, kwargs)).split()
    if op == "join":
        items = evaluate_expression(expr["items"], args, kwargs)
        if not isinstance(items, list):
            raise ProbeContractError("join expression requires list")
        return expr["separator"].join(str(item) for item in items)
    if op == "lower":
        return str(evaluate_expression(expr["value"], args, kwargs)).lower()
    if op == "upper":
        return str(evaluate_expression(expr["value"], args, kwargs)).upper()
    if op == "strip":
        return str(evaluate_expression(expr["value"], args, kwargs)).strip()
    if op == "length":
        return len(evaluate_expression(expr["value"], args, kwargs))
    raise ProbeContractError(f"unsupported expression at runtime: {op}")


def oracle_passes(outcome: dict | None, oracle: dict, case: dict) -> tuple[bool, str]:
    if not outcome or outcome.get("completed") is not True:
        return False, "no-complete-outcome"
    if oracle["kind"] == "raises":
        passed = outcome.get("kind") == "exception" and outcome.get("exception") == oracle["exception"]
        return passed, "expected-exception" if passed else "exception-mismatch"
    expected = evaluate_expression(oracle["expected"], case["args"], case["kwargs"])
    observed = outcome.get("value")
    passed = outcome.get("kind") == "return" and type(observed) is type(expected) and observed == expected
    return passed, "expected-return" if passed else "return-mismatch"
