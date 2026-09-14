from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import time

try:
    import resource
except ImportError:  # pragma: no cover
    resource = None


@dataclass(frozen=True)
class ExecutionResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    isolation: str = "process-timeout-resource-limits"
    security_sandbox: bool = False


class LocalFixtureExecutor:
    """Bounded executor for trusted deterministic showcase fixtures only.

    This is intentionally not a security sandbox. It applies timeout/resource
    limits and a scrubbed environment, but does not provide filesystem or
    network isolation. The runtime refuses non-fixture proposal sources.
    """

    def __init__(self, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _limits():
        if resource is None:
            return
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        if hasattr(resource, "RLIMIT_NOFILE"):
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        if hasattr(resource, "RLIMIT_NPROC"):
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            except (ValueError, OSError):
                pass

    def run(self, argv: list[str], cwd: Path) -> ExecutionResult:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                env=env,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                preexec_fn=self._limits if os.name == "posix" else None,
            )
            return ExecutionResult(
                argv=argv, returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
                timed_out=False, duration_ms=int((time.monotonic() - start) * 1000),
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                argv=argv, returncode=124, stdout=exc.stdout or "", stderr=exc.stderr or "",
                timed_out=True, duration_ms=int((time.monotonic() - start) * 1000),
            )
