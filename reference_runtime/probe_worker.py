from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

PREFIX = "REFERENCE_PROBE_RECEIPT="
RAW_PREFIX = "REFERENCE_RAW_OUTCOME="
_ALLOWED_EXCEPTIONS = {"ValueError", "TypeError", "KeyError"}
_ALLOWED_GENERATORS = {"random-name-whitespace", "blank-whitespace", "random-non-string"}
_ALLOWED_ORACLES = {"normalize-whitespace", "greet-normalized", "raises"}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _read_control(fd: int) -> dict:
    chunks: list[bytes] = []
    try:
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    value = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("control payload must be an object")
    return value


def _random_name() -> str:
    first = "N" + secrets.token_hex(5)
    last = "S" + secrets.token_hex(5)
    left = secrets.choice([" ", "  ", "\t", " \t"])
    middle = secrets.choice([" ", "   ", "\t", " \t "])
    right = secrets.choice([" ", "  ", "\t", "\t "])
    return f"{left}{first}{middle}{last}{right}"


def _blank_whitespace() -> str:
    return "".join(secrets.choice([" ", "\t", "\n"]) for _ in range(2 + secrets.randbelow(8)))


def _non_string() -> object:
    options: list[object] = [None, True, False, secrets.randbelow(1_000_000), -1 - secrets.randbelow(1_000_000)]
    return secrets.choice(options)


def _materialize_cases(probe: dict) -> list[dict]:
    cases = probe["cases"]
    generator = cases["generator"]
    count = cases["count"]
    if generator not in _ALLOWED_GENERATORS:
        raise ValueError(f"unsupported probe generator: {generator}")
    rows: list[dict] = []
    for index in range(count):
        if generator == "random-name-whitespace":
            value = _random_name()
        elif generator == "blank-whitespace":
            value = _blank_whitespace()
        else:
            value = _non_string()
        rows.append({"case": index + 1, "args": [value], "kwargs": {}})
    return rows


def _raw_outcome(child_stdout: str) -> tuple[dict | None, int]:
    lines = [line for line in child_stdout.splitlines() if line.startswith(RAW_PREFIX)]
    if len(lines) != 1:
        return None, len(lines)
    try:
        value = json.loads(lines[0][len(RAW_PREFIX):])
    except json.JSONDecodeError:
        return None, 1
    return value if isinstance(value, dict) else None, 1


def _oracle_passes(outcome: dict | None, oracle: dict, input_value: object) -> tuple[bool, str]:
    if not outcome or outcome.get("completed") is not True:
        return False, "no-complete-outcome"
    kind = oracle["kind"]
    if kind == "raises":
        expected = oracle["exception"]
        if expected not in _ALLOWED_EXCEPTIONS:
            return False, "unsupported-exception-oracle"
        return (
            outcome.get("kind") == "exception" and outcome.get("exception") == expected,
            "expected-exception" if outcome.get("kind") == "exception" and outcome.get("exception") == expected else "exception-mismatch",
        )
    if not isinstance(input_value, str):
        return False, "string-oracle-received-non-string"
    normalized = " ".join(input_value.split())
    if kind == "normalize-whitespace":
        expected_value = normalized
    elif kind == "greet-normalized":
        expected_value = f"Hello, {normalized}!"
    else:
        return False, "unsupported-oracle"
    passed = outcome.get("kind") == "return" and type(outcome.get("value")) is str and outcome.get("value") == expected_value
    return passed, "expected-return" if passed else "return-mismatch"


def _run_case(workspace: Path, probe: dict, case: dict) -> dict:
    child = Path(__file__).with_name("probe_child.py")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-S",
            str(child),
            "--workspace",
            str(workspace),
            "--target",
            probe["target"],
            "--callable",
            probe["callable"],
        ],
        cwd=workspace,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # Stay in the verifier worker's process group. The controller kills the
        # entire group on timeout, including this child and its descendants.
        start_new_session=False,
    )
    stdout, stderr = proc.communicate(input=_canonical({"args": case["args"], "kwargs": case["kwargs"]}))
    outcome, raw_receipt_count = _raw_outcome(stdout or "")
    passed, reason = _oracle_passes(outcome, probe["oracle"], case["args"][0])
    return {
        "case": case["case"],
        "input_sha256": hashlib.sha256(_canonical({"args": case["args"], "kwargs": case["kwargs"]}).encode()).hexdigest(),
        "input": case["args"][0],
        "child_exit_code": proc.returncode,
        "raw_outcome_count": raw_receipt_count,
        "outcome": outcome,
        "completed": bool(outcome and outcome.get("completed") is True and raw_receipt_count == 1),
        "passed": bool(passed and proc.returncode == 0 and raw_receipt_count == 1),
        "reason": reason if raw_receipt_count == 1 else "raw-outcome-count-invalid",
        "stderr_sha256": hashlib.sha256((stderr or "").encode()).hexdigest(),
    }


def _sign(receipt: dict, key: bytes) -> str:
    return hmac.new(key, _canonical(receipt).encode("utf-8"), hashlib.sha256).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--control-fd", type=int, required=True)
    args = parser.parse_args(argv)

    control = _read_control(args.control_fd)
    key = bytes.fromhex(control["receipt_key"])
    challenge = control["challenge"]
    probe = control["probe"]

    # The secret control fd is closed before any candidate process exists.
    # Candidate children receive only their current input, never the challenge,
    # HMAC key, oracle, generator definition or other future cases.
    cases = _materialize_cases(probe)
    rows = [_run_case(args.workspace.resolve(), probe, case) for case in cases]
    receipt = {
        "protocol": 2,
        "challenge": challenge,
        "probe_id": probe["id"],
        "completed": bool(rows) and all(row["completed"] for row in rows),
        "passed": bool(rows) and all(row["passed"] for row in rows),
        "case_count": len(rows),
        "cases": rows,
    }
    envelope = {"receipt": receipt, "hmac_sha256": _sign(receipt, key)}
    print(PREFIX + _canonical(envelope), flush=True)
    return 0 if receipt["completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
