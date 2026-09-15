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
    def merge_exact(self, base_sha: str, candidate_sha: str, message: str) -> str: ...
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

    def merge_exact(self, base_sha: str, candidate_sha: str, message: str) -> str:
        """Create a merge from exact revisions and CAS-update main.

        Branch names are deliberately not effect inputs. The detached merge binds
        the resulting commit to exact base/candidate objects; update-ref then
        advances main only if its ref still equals the reviewed base SHA.
        """
        self.git("checkout", "--detach", base_sha)
        self.git("merge", "--no-ff", candidate_sha, "-m", message)
        merge_sha = self.git("rev-parse", "HEAD")
        try:
            self.git("update-ref", "refs/heads/main", merge_sha, base_sha)
        except Exception:
            self.git("checkout", "main", check=False)
            raise
        self.git("checkout", "main")
        return merge_sha

    def merge(self, revision: str, message: str) -> str:
        """Compatibility shim for the internal v7 implementation.

        Public v7 uses merge_exact(). This fallback still resolves its input to an
        exact commit and uses the current main tip as a compare-and-swap base.
        """
        base_sha = self.git("rev-parse", "main")
        candidate_sha = self.git("rev-parse", revision)
        return self.merge_exact(base_sha, candidate_sha, message)

    def commit_control_state(self, paths: list[str], message: str) -> str:
        self.git("checkout", "main")
        for path in paths:
            self.git("add", path)
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")
