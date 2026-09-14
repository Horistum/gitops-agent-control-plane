from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .executor import ExecutionResult, LocalFixtureExecutor


class VerificationExecutionAdapter(Protocol):
    profile: str
    def run(self, argv: list[str], cwd: Path, **kwargs) -> ExecutionResult: ...


class GitEffectAdapter(Protocol):
    profile: str
    def find_trailer_effect(self, trailer_name: str, value: str) -> list[str]: ...
    def merge(self, branch: str, message: str) -> str: ...
    def commit_control_state(self, paths: list[str], message: str) -> str: ...


@dataclass
class LocalVerificationAdapter:
    executor: LocalFixtureExecutor
    profile: str = "standalone-local/v2"

    def run(self, argv: list[str], cwd: Path, **kwargs) -> ExecutionResult:
        return self.executor.run(argv, cwd, **kwargs)


@dataclass
class LocalGitEffectAdapter:
    git: Callable[..., str]
    profile: str = "standalone-local/v2"

    def find_trailer_effect(self, trailer_name: str, value: str) -> list[str]:
        marker = f"{trailer_name}: {value}"
        out = self.git("log", "--all", "--format=%H%x00%B%x00", capture=True)
        chunks = out.split("\x00")
        commits: list[str] = []
        for i in range(0, len(chunks) - 1, 2):
            sha, body = chunks[i].strip(), chunks[i + 1]
            trailing = [line.strip() for line in body.splitlines() if line.strip()]
            if sha and trailing and trailing[-1] == marker:
                commits.append(sha)
        return commits

    def merge(self, branch: str, message: str) -> str:
        self.git("checkout", "main")
        self.git("merge", "--no-ff", branch, "-m", message)
        return self.git("rev-parse", "HEAD")

    def commit_control_state(self, paths: list[str], message: str) -> str:
        self.git("checkout", "main")
        for path in paths:
            self.git("add", path)
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")
