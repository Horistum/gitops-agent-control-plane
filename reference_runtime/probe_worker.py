from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys

try:
    from .probe_dsl import materialize_cases, oracle_passes
except ImportError:  # executed as a standalone script
    from probe_dsl import materialize_cases, oracle_passes

PREFIX = "REFERENCE_PROBE_RECEIPT="
RAW_PREFIX = "REFERENCE_RAW_OUTCOME="


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


def _raw_outcome(child_stdout: str) -> tuple[dict | None, int]:
    lines = [line for line in child_stdout.splitlines() if line.startswith(RAW_PREFIX)]
    if len(lines) != 1:
        return None, len(lines)
    try:
        value = json.loads(lines[0][len(RAW_PREFIX):])
    except json.JSONDecodeError:
        return None, 1
    return value if isinstance(value, dict) else None, 1


def _run_case(workspace: Path, probe: dict, case: dict) -> dict:
    child = Path(__file__).with_name("probe_child.py")
    payload = {"args": case["args"], "kwargs": case["kwargs"]}
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
        start_new_session=False,
    )
    stdout, stderr = proc.communicate(input=_canonical(payload))
    child_stdout = stdout or ""
    outcome, raw_outcome_count = _raw_outcome(child_stdout)
    passed, reason = oracle_passes(outcome, probe["oracle"], case)
    final_receipt_injection_count = sum(
        1 for line in child_stdout.splitlines() if line.startswith(PREFIX)
    )
    return {
        "case": case["case"],
        "input_sha256": hashlib.sha256(_canonical(payload).encode()).hexdigest(),
        "child_exit_code": proc.returncode,
        "raw_outcome_count": raw_outcome_count,
        "candidate_receipt_injection_count": final_receipt_injection_count,
        "outcome": outcome,
        "completed": bool(outcome and outcome.get("completed") is True and raw_outcome_count == 1),
        "passed": bool(passed and proc.returncode == 0 and raw_outcome_count == 1),
        "reason": reason if raw_outcome_count == 1 else "raw-outcome-count-invalid",
        "stdout_sha256": hashlib.sha256(child_stdout.encode()).hexdigest(),
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

    # The control fd is closed before candidate code exists. The trusted parent
    # owns case generation and oracle evaluation. Candidate stdout is captured
    # as untrusted observation and never forwarded into the final receipt stream.
    cases = materialize_cases(probe)
    rows = [_run_case(args.workspace.resolve(), probe, case) for case in cases]
    receipt = {
        "protocol": 3,
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
