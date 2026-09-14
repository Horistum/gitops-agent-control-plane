from __future__ import annotations

import argparse
import builtins
import importlib.util
import json
import os
from pathlib import Path
import sys

_ORIGINAL_GETATTR = builtins.getattr
_ORIGINAL_JSON_DUMPS = json.dumps
_ORIGINAL_OS_WRITE = os.write
_ORIGINAL_TYPE = builtins.type
_RAW_PREFIX = "REFERENCE_RAW_OUTCOME="
_ALLOWED_RETURN_TYPES = {str, int, float, bool, type(None)}


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


def _load_module(target: Path):
    spec = importlib.util.spec_from_file_location("_reference_probe_target", target)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot create probe module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _emit(value: dict) -> None:
    raw = _RAW_PREFIX + _ORIGINAL_JSON_DUMPS(value, sort_keys=True, separators=(",", ":")) + "\n"
    _ORIGINAL_OS_WRITE(1, raw.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--callable", dest="callable_name", required=True)
    args = parser.parse_args(argv)

    # Input is read and stdin is detached before candidate code is imported.
    payload = json.loads(sys.stdin.read())
    sys.stdin = open(os.devnull, "r")
    # Candidate stdout/stderr are discarded. The wrapper keeps fd 1 itself as
    # the raw outcome channel through the captured os.write reference.
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

    outcome: dict
    try:
        module = _load_module(_target(args.workspace.resolve(), args.target))
        function = _ORIGINAL_GETATTR(module, args.callable_name, None)
        if not callable(function):
            outcome = {"completed": True, "kind": "missing-callable"}
        else:
            try:
                value = function(*payload.get("args", []), **payload.get("kwargs", {}))
            except BaseException as exc:
                outcome = {
                    "completed": True,
                    "kind": "exception",
                    "exception": _ORIGINAL_TYPE(exc).__name__,
                }
            else:
                if _ORIGINAL_TYPE(value) not in _ALLOWED_RETURN_TYPES:
                    outcome = {
                        "completed": True,
                        "kind": "unsupported-return",
                        "return_type": _ORIGINAL_TYPE(value).__name__,
                    }
                else:
                    outcome = {
                        "completed": True,
                        "kind": "return",
                        "return_type": _ORIGINAL_TYPE(value).__name__,
                        "value": value,
                    }
    except BaseException as exc:
        outcome = {
            "completed": True,
            "kind": "child-error",
            "error_type": _ORIGINAL_TYPE(exc).__name__,
        }

    _emit(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
