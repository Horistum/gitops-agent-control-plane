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
    """Bounded POSIX executor for trusted deterministic fixtures only.

    It bounds wall-clock/CPU/process resources and cleans the spawned process
    group, but it is deliberately not a filesystem/network security sandbox.
    A controller payload can be delivered through an inherited pipe only after
    the reader process has started, avoiding a pre-spawn pipe-buffer deadlock.
    """

    def __init__(self, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds
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

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise RuntimeError("controller pipe write made no progress")
            offset += written

    def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        env_extra: dict[str, str] | None = None,
        pass_fds: tuple[int, ...] = (),
        control_payload: bytes | None = None,
        control_fd_flag: str = "--control-fd",
    ) -> ExecutionResult:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        if env_extra:
            env.update(env_extra)

        read_fd: int | None = None
        write_fd: int | None = None
        effective_argv = list(argv)
        inherited = tuple(pass_fds)
        if control_payload is not None:
            if os.name != "posix":
                raise RuntimeError("inherited verifier control channel requires POSIX")
            read_fd, write_fd = os.pipe()
            effective_argv.extend([control_fd_flag, str(read_fd)])
            inherited = tuple(dict.fromkeys((*inherited, read_fd)))

        start = time.monotonic()
        popen_kwargs: dict = {
            "cwd": cwd,
            "text": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.DEVNULL,
            "env": env,
            "start_new_session": True,
            "preexec_fn": self._limits if os.name == "posix" else None,
        }
        if os.name == "posix":
            popen_kwargs["pass_fds"] = inherited
        elif inherited:
            raise RuntimeError("pass_fds requires POSIX")

        try:
            proc = subprocess.Popen(effective_argv, **popen_kwargs)
        except Exception:
            if read_fd is not None:
                os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)
            raise

        if read_fd is not None:
            os.close(read_fd)
        if write_fd is not None:
            try:
                self._write_all(write_fd, control_payload or b"")
            except BrokenPipeError:
                pass
            finally:
                os.close(write_fd)

        timed_out = False
        group_terminated = False
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            group_terminated = self._kill_process_group(proc)
            stdout, stderr = proc.communicate()
        else:
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
            argv=effective_argv,
            returncode=returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            timed_out=timed_out,
            duration_ms=int((time.monotonic() - start) * 1000),
            process_group_terminated=group_terminated,
            cpu_limit_seconds=self.cpu_limit_seconds,
        )
