from __future__ import annotations

import argparse
import builtins
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

PREFIX = "REFERENCE_PROBE_RECEIPT="
_ORIGINAL_PRINT = builtins.print
_ORIGINAL_GETATTR = builtins.getattr
_ORIGINAL_TYPE = builtins.type
_ORIGINAL_JSON_DUMPS = json.dumps
_ORIGINAL_STDOUT = sys.stdout
_EXPECTED_EXCEPTIONS = {
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
}


def _target(workspace: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise ValueError("unsafe probe target")
    target = (workspace / relative).resolve()
    root = workspace.resolve()
    if root not in target.parents:
        raise ValueError("probe target escapes workspace")
    if not target.is_file() or target.is_symlink():
        raise ValueError("probe target must be a regular file")
    return target


def _hygiene_snapshot() -> dict[str, object]:
    return {
        "unittest.assertEqual": unittest.TestCase.assertEqual,
        "unittest.assertRaises": unittest.TestCase.assertRaises,
        "unittest.addSuccess": unittest.TestResult.addSuccess,
        "ElementTree.write": ET.ElementTree.write,
        "json.dumps": json.dumps,
        "builtins.print": builtins.print,
        "builtins.getattr": builtins.getattr,
        "builtins.type": builtins.type,
    }


def _hygiene_ok(before: dict[str, object]) -> tuple[bool, list[str]]:
    after = _hygiene_snapshot()
    changed = sorted(name for name, value in before.items() if after[name] is not value)
    return not changed, changed


def _load_module(target: Path):
    spec = importlib.util.spec_from_file_location("_reference_probe_target", target)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot create probe module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _return_matches(value: object, expected: object) -> bool:
    # The standalone probe contract deliberately supports JSON scalar returns.
    # Exact builtin type identity avoids candidate-controlled __eq__ objects.
    if _ORIGINAL_TYPE(expected) not in {str, int, float, bool, type(None)}:
        return False
    return _ORIGINAL_TYPE(value) is _ORIGINAL_TYPE(expected) and value == expected


def execute(workspace: Path, probe: dict, nonce: str) -> dict:
    result = {
        "protocol": 1,
        "nonce": nonce,
        "probe_id": probe.get("id"),
        "completed": False,
        "passed": False,
        "reason": None,
        "hygiene_ok": False,
        "hygiene_changes": [],
    }
    before = _hygiene_snapshot()
    try:
        target = _target(workspace, probe["target"])
        module = _load_module(target)
        hygiene_ok, changes = _hygiene_ok(before)
        result["hygiene_ok"] = hygiene_ok
        result["hygiene_changes"] = changes
        if not hygiene_ok:
            result["reason"] = "import-hygiene-changed"
            result["completed"] = True
            return result
        function = _ORIGINAL_GETATTR(module, probe["callable"], None)
        if not callable(function):
            result["reason"] = "missing-callable"
            result["completed"] = True
            return result
        expect = probe["expect"]
        try:
            value = function(*probe.get("args", []), **probe.get("kwargs", {}))
        except BaseException as exc:  # includes SystemExit; os._exit leaves no receipt
            expected_type = _EXPECTED_EXCEPTIONS.get(expect.get("exception"))
            if expected_type is not None and _ORIGINAL_TYPE(exc) is expected_type:
                result["passed"] = True
                result["reason"] = "expected-exception"
                result["observed_exception"] = expected_type.__name__
            else:
                result["reason"] = "unexpected-exception"
                result["observed_exception"] = _ORIGINAL_TYPE(exc).__name__
        else:
            if "return" in expect and _return_matches(value, expect["return"]):
                result["passed"] = True
                result["reason"] = "expected-return"
            elif "exception" in expect:
                result["reason"] = "expected-exception-not-raised"
            else:
                result["reason"] = "return-mismatch"
            try:
                _ORIGINAL_JSON_DUMPS(value)
                result["observed_return"] = value
            except (TypeError, ValueError):
                result["observed_return_repr"] = repr(value)
        hygiene_ok, changes = _hygiene_ok(before)
        result["hygiene_ok"] = hygiene_ok
        result["hygiene_changes"] = changes
        if not hygiene_ok:
            result["passed"] = False
            result["reason"] = "execution-hygiene-changed"
        result["completed"] = True
        return result
    except BaseException as exc:
        result["completed"] = True
        result["reason"] = "worker-error"
        result["worker_error"] = f"{_ORIGINAL_TYPE(exc).__name__}: {exc}"
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--probe-json", required=True)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args(argv)
    probe = json.loads(args.probe_json)
    result = execute(args.workspace.resolve(), probe, args.nonce)
    _ORIGINAL_PRINT(
        PREFIX + _ORIGINAL_JSON_DUMPS(result, sort_keys=True, separators=(",", ":")),
        file=_ORIGINAL_STDOUT,
        flush=True,
    )
    return 0 if result["completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
