from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
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
    isolation: str = "process-group-timeout-resource-limits"
    security_sandbox: bool = False
    process_group_terminated: bool = False
    cpu_limit_seconds: int | None = None


class LocalFixtureExecutor:
    """Bounded Linux executor for trusted deterministic fixtures only.

    It bounds wall-clock/CPU/process resources and cleans the spawned process
    group, but it is deliberately not a filesystem/network security sandbox.
    """

    def __init__(self, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds
        # Keep the controller wall-clock timeout authoritative. CPU is a
        # backstop one second later rather than a hidden hard-coded limit.
        self.cpu_limit_seconds = timeout_seconds + 1

    def _limits(self) -> None:
        if resource is None:
            return
        cpu = self.cpu_limit_seconds
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        if hasattr(resource, "RLIMIT_NOFILE"):
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        if hasattr(resource, "RLIMIT_NPROC"):
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            except (ValueError, OSError):
                pass

    @staticmethod
    def _kill_process_group(proc: subprocess.Popen) -> bool:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                return True
            except ProcessLookupError:
                return False
        if proc.poll() is None:
            proc.kill()
            return True
        return False

    def run(self, argv: list[str], cwd: Path, *, env_extra: dict[str, str] | None = None) -> ExecutionResult:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        if env_extra:
            env.update(env_extra)
        start = time.monotonic()
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
            preexec_fn=self._limits if os.name == "posix" else None,
        )
        timed_out = False
        group_terminated = False
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            group_terminated = self._kill_process_group(proc)
            stdout, stderr = proc.communicate()
        else:
            # A direct child may exit while leaving grandchildren alive. Clean
            # its dedicated process group after capturing the direct result.
            group_terminated = self._kill_process_group(proc)
        returncode = proc.returncode
        if returncode is None:
            returncode = 124 if timed_out else -1
        if timed_out:
            returncode = 124
        elif returncode == -getattr(signal, "SIGXCPU", 24):
            timed_out = True
            returncode = 124
        return ExecutionResult(
            argv=argv,
            returncode=returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            timed_out=timed_out,
            duration_ms=int((time.monotonic() - start) * 1000),
            process_group_terminated=group_terminated,
            cpu_limit_seconds=self.cpu_limit_seconds,
        )
