"""Bounded, non-authoritative failure reports shared by logs, CLI and review UI.

Unknown exceptions keep their type, causal chain and stack locations. Never
capture locals, source lines, request bodies or authentication headers.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import math
from pathlib import Path
import re
import stat
import uuid

from control_plane_core import CoreError, fingerprint
from .io import Closed, Unavailable, canonical, loads, locked

LOG_NAME = "diagnostics.jsonl"
LOG_LIMIT = 1_000_000
_SECRET_NAME = re.compile(r"key|token|secret|password|credential|authorization", re.I)
_ENV_SECRET_NAME = re.compile(r"(?:^|_)(?:key|token|secret|password|passwd|credentials?|authorization)$", re.I)


def secret_values(environment=None):
    return [value for name, value in (os.environ if environment is None else environment).items()
            if _ENV_SECRET_NAME.search(name) and isinstance(value, str) and value]


def safe_text(value, *, secrets=(), limit=2000):
    text = str(value)
    explicit = {secret for secret in secrets if isinstance(secret, str) and secret}
    values = explicit | set(secret_values())
    patterns = []
    for secret in sorted(values, key=lambda value: (-len(value), value)):
        literal = re.escape(secret)
        # Environment names are a heuristic, not proof of credential identity.
        # Short inferred values must not corrupt a run ID, SHA or ordinary word.
        # Resolved/explicit credentials retain exact substring masking at any size.
        patterns.append(literal if secret in explicit or len(secret) >= 8 else
                        r"(?<!\w)" + literal + r"(?!\w)")
    if patterns:
        # One pass prevents one secret from rewriting another's redaction marker.
        text = re.sub("|".join(patterns) + r"|\[redacted\]",
                      lambda match: "[redacted]", text)
    # Redact complete known values before cutting a window, then bound regex
    # work even for a subprocess emitting megabytes of unbroken text.
    truncated = len(text) > max(8192, limit * 2)
    text = text[:max(8192, limit * 2)]
    text = re.sub(r"(?i)\bBearer\s+[^\s\"',;]+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)\b((?:[\w-]*(?:api[_-]?key|token|secret|password|credential|authorization))[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
                  r"\1[redacted]", text)
    text = re.sub(r"\b(?:sk-[\w-]{8,}|gh[pousr]_[\w]+|github_pat_[\w]+)\b", "[redacted]", text)
    text = re.sub(r"(https?://)[^/\s@]+@", r"\1[redacted]@", text)
    text = re.sub(r"(https?://[^\s?#]+)\?[^\s]+", r"\1?[redacted]", text)
    text = "".join(c if c in "\n\t" or ord(c) >= 32 and ord(c) != 127 else "?" for c in text)
    return text[:limit] + (" …[truncated]" if truncated or len(text) > limit else "")


def safe_data(value, *, secrets=(), depth=0):
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        return {safe_text(k, secrets=secrets, limit=100):
                ("[redacted]" if _SECRET_NAME.search(str(k)) else safe_data(v, secrets=secrets, depth=depth + 1))
                for k, v in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [safe_data(v, secrets=secrets, depth=depth + 1) for v in value[:20]]
    if type(value) is float and not math.isfinite(value):
        return str(value)
    if value is None or type(value) in (bool, int, float):
        return value
    return safe_text(value, secrets=secrets)


def recovery_steps(code, state):
    pending = state.get("pending") or {}
    if code == "AUTHORITY_CHANGED":
        return ["Restore the exact authorized policy and goal snapshot, or prepare a separately authorized run. Do not rewrite its hash."]
    if code == "RUNTIME_CHANGED":
        steps = ["Pause this run with the installed controller; pause does not accept the new runtime."] if not state.get("paused") else []
        return steps + ["Resolve pending effects using the original runtime, if present. Then use upgrade at a quiescent boundary.",
                        "Upgrade requires no active task, or --suspend for an eligible unchanged held attempt. Continue only after the upgrade succeeds."]
    if pending.get("kind") == "model":
        return ["The previous model call may have executed. Inspect its exact pending effect and receipt before continuing.",
                "Use reconcile-effect with a restored valid receipt. Without a receipt, retry-effect explicitly authorizes another potentially charged call."]
    if pending:
        return ["Reconcile the pending external effect before retrying, replanning or upgrading."]
    hints = {
        "REASONING_EXECUTABLE_UNAVAILABLE": "Restore the executable named by the saved reasoning argv and check its path and execute permission; then run one tick.",
        "CREDENTIALS_UNAVAILABLE": "Restore the configured credential source or broker, run doctor, then run one tick. No model call was reserved during preparation.",
        "MODEL_BUDGET_EXHAUSTED": "The owner must decide whether to authorize further work. Replan does not reset this run's lifetime budget.",
        "DISCOVERY_NOT_SELECTED": "Inspect discovery feedback, eligible IDs and source context. Correct the cause, then replan if the remaining budget permits it.",
        "CONTEXT_LIMIT": "Inspect context/protocol feedback and omitted files. Remove the cause of repeated requests before a permitted replan.",
        "RECEIPT_MISSING": "Restore the original receipt from a verified backup; do not invent a result or repeat a recorded effect.",
        "APPROVAL_REQUIRED": "Review the exact candidate and evidence, then approve its binding or choose a permitted replan/cancel action.",
        "VERIFICATION_FAILED": "Inspect the failed verification evidence. Retry only a retryable hold after fixing its cause, or use a permitted replan.",
        "UNEXPECTED_ERROR": "Use the diagnostic ID, exception chain and stack locations to investigate the controller failure before resuming.",
        "EXTERNAL_UNAVAILABLE": "Restore the unavailable dependency, then run one tick to observe it again.",
    }
    return [hints.get(code, "Inspect the message, exception details and current decision. Correct the cause before choosing an allowed recovery action.")]


def failure_code(exc, kind=None):
    if getattr(exc, "code", None):
        return exc.code
    if isinstance(exc, Unavailable):
        return "EXTERNAL_UNAVAILABLE"
    if isinstance(exc, (Closed, CoreError)):
        return "POLICY_BLOCKED"
    if exc is not None:
        return "UNEXPECTED_ERROR"
    return {"NEEDS_DECISION": "APPROVAL_REQUIRED", "FAILED": "VERIFICATION_FAILED"}.get(kind, "POLICY_BLOCKED")


def describe(state=None, *, exc=None, message=None, operation="tick", phase=None, kind=None, secrets=()):
    state = state if isinstance(state, dict) else {}
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    code = failure_code(exc, kind)
    chain, seen = [], set()
    current = exc
    while current is not None and id(current) not in seen and len(chain) < 5:
        seen.add(id(current))
        frames, tb = [], current.__traceback__
        while tb is not None:
            frame = tb.tb_frame
            frames.append({"file": "/".join(Path(frame.f_code.co_filename).parts[-2:]),
                           "line": tb.tb_lineno, "function": frame.f_code.co_name})
            tb = tb.tb_next
        chain.append({"type": type(current).__name__, "message": safe_text(current, secrets=secrets), "frames": frames[-12:]})
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
    discovery = state.get("discovery") if isinstance(state.get("discovery"), dict) else {}
    return {"schema": 1, "id": uuid.uuid4().hex, "at": datetime.now(timezone.utc).isoformat(),
            "code": code, "message": safe_text(message if message is not None else exc, secrets=secrets) or type(exc).__name__,
            "operation": safe_text(operation, secrets=secrets, limit=200),
            "phase": safe_data(phase or task.get("phase", state.get("phase")), secrets=secrets),
            "run_id": safe_data(state.get("run_id"), secrets=secrets), "revision": safe_data(state.get("revision")),
            "item": safe_data(task.get("id"), secrets=secrets),
            "head": safe_data(task.get("head", discovery.get("head", state.get("base"))), secrets=secrets),
            "pending_effect": safe_data({"id": pending.get("id"), "kind": pending.get("kind")}, secrets=secrets) if pending else None,
            "exception": chain, "details": safe_data(getattr(exc, "details", {}), secrets=secrets),
            "next_steps": recovery_steps(code, {**state, "pending": pending})}


def append_event(root, diagnostic):
    """Best-effort private log. A logging failure never replaces the real error."""
    root = Path(root)
    try:
        if not root.is_dir():
            return False
        with locked(root / "diagnostic-log"):
            path = root / LOG_NAME
            if path.exists():
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    return False
                if info.st_size >= LOG_LIMIT:
                    os.replace(path, root / (LOG_NAME + ".1"))
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    return False
                os.fchmod(fd, 0o600)
                data = canonical(diagnostic) + b"\n"
                with os.fdopen(fd, "ab", closefd=False) as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                os.close(fd)
        return True
    except (OSError, ValueError, Closed):
        return False


def record(root, state, **kwargs):
    value = describe(state, **kwargs)
    value["log_written"] = True
    value["log_written"] = append_event(root, value)
    return value


def current_diagnostic(state):
    """Read-only observation, including drift before Controller can be built."""
    from .store import runtime_fingerprint
    if state.get("policy_hash") != fingerprint({"policy": state.get("policy"), "goal": state.get("goal")}):
        exc = Closed("Saved authority snapshot changed", code="AUTHORITY_CHANGED")
    elif state.get("runtime_hash") != runtime_fingerprint():
        exc = Closed("Runtime changed; pause, then use the explicit quiescent upgrade command", code="RUNTIME_CHANGED",
                     details={"saved_runtime_hash": state.get("runtime_hash"), "current_runtime_hash": runtime_fingerprint()})
    else:
        return state.get("diagnostic")
    value = describe(state, exc=exc, operation="observe")
    # Reads must not create new events or invalidate the same displayed decision.
    value["id"] = fingerprint({"run_id": state.get("run_id"), "code": exc.code, "details": exc.details})[:32]
    value["at"] = None
    return value


def recent_events(root, limit=20):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise Closed("Diagnostic limit must be between 1 and 100")
    events = []
    for suffix in (".1", ""):
        path = Path(root) / (LOG_NAME + suffix)
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size > LOG_LIMIT + 100_000:
            raise Closed("Expected a bounded regular diagnostic log")
        for line in path.read_bytes().splitlines():
            try:
                value = loads(line)
            except (ValueError, Closed):
                continue  # A partial final write must not hide earlier diagnostics.
            if isinstance(value, dict) and value.get("schema") == 1:
                events.append(value)
        events = events[-limit:]
    return {"events": events, "log": LOG_NAME}


def error_response(root, exc, *, operation, secrets=()):
    from .store import Store
    try:
        state = Store(root).state if root is not None else {}
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}
    value = describe(state, exc=exc, operation=operation, secrets=secrets)
    value["log_written"] = True
    value["log_written"] = append_event(root, value) if root is not None else False
    return {"status": "BLOCKED", "reason": value["message"], "diagnostic": value}


def provider_error(exc, *, provider, key=""):
    """Opt-in adapter stderr protocol; bounded selected fields, never headers."""
    from urllib.error import HTTPError, URLError
    details = {"provider": provider, "exception_type": type(exc).__name__}
    code, message = "PROVIDER_ERROR", safe_text(exc, secrets=(key,))
    if isinstance(exc, HTTPError):
        code, message = "PROVIDER_HTTP_ERROR", f"{provider} returned HTTP {exc.code}"
        details["http_status"] = exc.code
        if exc.headers:
            details["request_id"] = safe_text(exc.headers.get("request-id") or exc.headers.get("x-request-id") or "", secrets=(key,), limit=200)
        try:
            body = exc.read(32_001)
            value = loads(body) if len(body) <= 32_000 else {}
            problem = value.get("error") if isinstance(value, dict) else None
            if isinstance(problem, dict):
                details["provider_error_type"] = safe_text(problem.get("type", ""), secrets=(key,), limit=200)
                detail = problem.get("message")
                if isinstance(detail, str):
                    message += ": " + safe_text(detail, secrets=(key,))
        except Exception:
            pass  # HTTP status remains useful when the body is not readable JSON.
    elif isinstance(exc, URLError):
        code = "PROVIDER_TRANSPORT_ERROR"
    return {"schema": "provider-error/v1", "code": code, "message": message,
            "details": safe_data(details, secrets=(key,))}


def command_failure(result, *, executable, secrets=()):
    """Treat subprocess diagnostics as untrusted explanation, never authority."""
    details = {"executable": Path(executable).name, "exit_code": result.returncode}
    excerpt = safe_text(result.stderr.decode("utf-8", "replace"), secrets=secrets)
    message, code = f"Reasoning command {Path(executable).name} exited {result.returncode}", "PROVIDER_COMMAND_FAILED"
    try:
        value = loads(result.stderr) if len(result.stderr) <= 32_000 else None
    except (ValueError, Closed):
        value = None
    if isinstance(value, dict) and value.get("schema") == "provider-error/v1" and isinstance(value.get("message"), str):
        message += ": " + safe_text(value["message"], secrets=secrets)
        details["provider_error"] = safe_data(value, secrets=secrets)
    elif excerpt:
        details["stderr_excerpt"] = excerpt
    return Unavailable(message, code=code, details=details)
