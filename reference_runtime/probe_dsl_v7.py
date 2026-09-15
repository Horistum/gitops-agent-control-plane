from __future__ import annotations

from typing import Any

try:
    from . import _probe_dsl_impl as _impl
except ImportError:  # standalone probe worker import path
    import _probe_dsl_impl as _impl

ProbeContractError = _impl.ProbeContractError
MAX_GENERATOR_DEPTH = 32
MAX_EXPRESSION_DEPTH = 64


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise ProbeContractError(f"unsupported literal/constant type: {type(value).__name__}")


def _assert_generator_depth(spec: Any, depth: int = 0) -> None:
    if depth > MAX_GENERATOR_DEPTH:
        raise ProbeContractError(f"generator nesting exceeds {MAX_GENERATOR_DEPTH}")
    if not isinstance(spec, dict):
        return
    if spec.get("kind") == "choice" and isinstance(spec.get("options"), list):
        for option in spec["options"]:
            _assert_generator_depth(option, depth + 1)


def _assert_expression_depth(expr: Any, depth: int = 0) -> None:
    if depth > MAX_EXPRESSION_DEPTH:
        raise ProbeContractError(f"expression nesting exceeds {MAX_EXPRESSION_DEPTH}")
    if not isinstance(expr, dict):
        return
    op = expr.get("op")
    if op == "concat" and isinstance(expr.get("parts"), list):
        for part in expr["parts"]:
            _assert_expression_depth(part, depth + 1)
    elif op == "join":
        _assert_expression_depth(expr.get("items"), depth + 1)
    elif op in {"split-whitespace", "lower", "upper", "strip", "length"}:
        _assert_expression_depth(expr.get("value"), depth + 1)


def validate_generator(spec: dict, *, where: str = "generator") -> None:
    _assert_generator_depth(spec)
    try:
        _impl.validate_generator(spec, where=where)
    except RecursionError as exc:
        raise ProbeContractError(f"{where} nesting exceeds supported depth") from exc


def validate_expression(expr: dict, *, where: str = "expression") -> None:
    _assert_expression_depth(expr)
    try:
        _impl.validate_expression(expr, where=where)
    except RecursionError as exc:
        raise ProbeContractError(f"{where} nesting exceeds supported depth") from exc


def _generator_types(spec: dict) -> set[str]:
    kind = spec["kind"]
    if kind == "constant":
        return {_json_type(spec["value"])}
    if kind == "null":
        return {"null"}
    if kind == "boolean":
        return {"boolean"}
    if kind == "integer":
        return {"integer"}
    if kind in {"whitespace", "text-tokens"}:
        return {"string"}
    if kind == "choice":
        result: set[str] = set()
        for option in spec["options"]:
            result.update(_generator_types(option))
        return result
    raise ProbeContractError(f"unsupported generator for type inference: {kind}")


def _expression_types(
    expr: dict,
    *,
    arg_types: list[set[str]],
    kwarg_types: dict[str, set[str]],
    where: str,
    depth: int = 0,
) -> set[str]:
    if depth > MAX_EXPRESSION_DEPTH:
        raise ProbeContractError(f"{where} nesting exceeds {MAX_EXPRESSION_DEPTH}")
    op = expr["op"]
    if op == "literal":
        return {_json_type(expr["value"])}
    if op == "arg":
        index = expr["index"]
        if index >= len(arg_types):
            raise ProbeContractError(
                f"{where}.index {index} out of range for {len(arg_types)} positional case arguments"
            )
        return set(arg_types[index])
    if op == "kwarg":
        name = expr["name"]
        if name not in kwarg_types:
            raise ProbeContractError(f"{where}.name {name!r} is not defined by probe.cases.kwargs")
        return set(kwarg_types[name])
    if op == "concat":
        for i, part in enumerate(expr["parts"]):
            _expression_types(
                part,
                arg_types=arg_types,
                kwarg_types=kwarg_types,
                where=f"{where}.parts[{i}]",
                depth=depth + 1,
            )
        return {"string"}
    if op == "split-whitespace":
        _expression_types(
            expr["value"], arg_types=arg_types, kwarg_types=kwarg_types,
            where=f"{where}.value", depth=depth + 1,
        )
        return {"array"}
    if op == "join":
        item_types = _expression_types(
            expr["items"], arg_types=arg_types, kwarg_types=kwarg_types,
            where=f"{where}.items", depth=depth + 1,
        )
        if item_types != {"array"}:
            raise ProbeContractError(f"{where}.items must statically evaluate to an array, got {sorted(item_types)}")
        return {"string"}
    if op in {"lower", "upper", "strip"}:
        _expression_types(
            expr["value"], arg_types=arg_types, kwarg_types=kwarg_types,
            where=f"{where}.value", depth=depth + 1,
        )
        return {"string"}
    if op == "length":
        value_types = _expression_types(
            expr["value"], arg_types=arg_types, kwarg_types=kwarg_types,
            where=f"{where}.value", depth=depth + 1,
        )
        allowed = {"string", "array", "object"}
        if not value_types or not value_types <= allowed:
            raise ProbeContractError(
                f"{where}.value must be sized (string/array/object), got {sorted(value_types)}"
            )
        return {"integer"}
    raise ProbeContractError(f"unsupported expression op during type inference: {op}")


def validate_probe(probe: dict) -> None:
    if isinstance(probe, dict):
        cases = probe.get("cases")
        if isinstance(cases, dict):
            for generator in cases.get("args", []) if isinstance(cases.get("args"), list) else []:
                _assert_generator_depth(generator)
            for binding in cases.get("kwargs", []) if isinstance(cases.get("kwargs"), list) else []:
                if isinstance(binding, dict):
                    _assert_generator_depth(binding.get("generator"))
        oracle = probe.get("oracle")
        if isinstance(oracle, dict) and oracle.get("kind") == "return-equals":
            _assert_expression_depth(oracle.get("expected"))
    try:
        _impl.validate_probe(probe)
    except RecursionError as exc:
        raise ProbeContractError("probe nesting exceeds supported depth") from exc

    cases = probe["cases"]
    arg_types = [_generator_types(spec) for spec in cases["args"]]
    kwarg_types = {
        binding["name"]: _generator_types(binding["generator"])
        for binding in cases["kwargs"]
    }
    oracle = probe["oracle"]
    if oracle["kind"] == "return-equals":
        _expression_types(
            oracle["expected"],
            arg_types=arg_types,
            kwarg_types=kwarg_types,
            where="probe.oracle.expected",
        )


# Runtime execution remains in the stable v6 implementation. The v7 layer only
# strengthens contract validation before any worker process receives a probe.
generate_value = _impl.generate_value
materialize_cases = _impl.materialize_cases
evaluate_expression = _impl.evaluate_expression
oracle_passes = _impl.oracle_passes
SUPPORTED_EXCEPTIONS = _impl.SUPPORTED_EXCEPTIONS
SUPPORTED_GENERATORS = _impl.SUPPORTED_GENERATORS
SUPPORTED_EXPR_OPS = _impl.SUPPORTED_EXPR_OPS
