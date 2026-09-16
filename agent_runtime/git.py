"""Real immutable Git snapshots and deterministic, controller-owned commits."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import re
import tempfile

from control_plane_core import path_allowed, require_merge_identity
from .io import Closed, digest, run


def safe_path(path):
    if not path_allowed(path, ["*"]):
        raise Closed("Unsafe repository path")
    return path


def sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value or ""):
        raise Closed("Expected exact Git SHA-1")
    return value


class GitRepository:
    def __init__(self, directory, branch):
        self.directory, self.branch = Path(directory), branch

    def command(self, *args, data=b"", env=None, check=True, limit=8_000_000):
        environment = os.environ.copy()
        environment.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1")
        environment.update(env or {})
        return run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(self.directory), *args],
                   data=data, env=environment, check=check, timeout=120, limit=limit)

    def text(self, *args, **kwargs):
        return self.command(*args, **kwargs).stdout.decode().strip()

    @classmethod
    def initialize(cls, product, directory, policy):
        source = cls(product, policy["base_branch"])
        source.text("check-ref-format", "refs/heads/" + source.branch)
        if source.text("status", "--porcelain", "--untracked-files=all"):
            raise Closed("Start from a clean product checkout")
        expected = source.resolve(source.branch)
        directory = Path(directory)
        if directory.exists():
            raise Closed("Run repository already exists; resume the existing run")
        run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--bare", "--no-hardlinks",
             "--", str(Path(product).resolve()), str(directory)], timeout=120)
        repo = cls(directory, source.branch)
        if repo.resolve(source.branch) != expected:
            raise Closed("Product moved during initialization")
        repo.text("config", "core.hooksPath", "/dev/null")
        if policy["publication"]["kind"] == "github":
            slug = policy["publication"]["repository"]
            remote = source.text("remote", "get-url", "origin")
            if remote not in {f"https://github.com/{slug}.git", f"git@github.com:{slug}.git", f"https://github.com/{slug}"}:
                raise Closed("Product origin differs from authorized GitHub repository")
            repo.text("remote", "set-url", "origin", remote)
            repo.text("config", "--unset-all", "remote.origin.fetch", check=False)
            repo.text("config", "--add", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
            if repo.remote_base() != expected:
                raise Closed("Local product base is not current remote base")
        return repo

    def resolve(self, revision):
        return sha(self.text("rev-parse", "--verify", revision + "^{commit}"))

    def remote_base(self):
        self.text("fetch", "--no-tags", "origin", "refs/heads/" + self.branch)
        return self.resolve("FETCH_HEAD")

    def tree(self, revision):
        result = {}
        for record in self.command("ls-tree", "-rz", sha(revision)).stdout.split(b"\0"):
            if not record:
                continue
            meta, raw_path = record.split(b"\t", 1)
            mode, kind, blob = meta.decode().split()
            path = safe_path(raw_path.decode())
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise Closed("Operational snapshots refuse symlinks and submodules: " + path)
            result[path] = (mode, blob)
        return result

    def read(self, revision, path):
        entries = self.tree(revision)
        if path not in entries:
            return None
        size = int(self.text("cat-file", "-s", entries[path][1]))
        if size > 8_000_000:
            raise Closed("Source blob exceeds snapshot limit")
        return self.command("cat-file", "blob", entries[path][1], limit=8_000_001).stdout

    def context(self, revision, paths, maximum):
        tree = self.tree(revision)
        result, used = {}, 0
        for query in paths:
            match = re.fullmatch(r"(.+)#L([1-9][0-9]*)-L([1-9][0-9]*)", query)
            path = match[1] if match else query
            safe_path(path)
            if match and not int(match[2]) <= int(match[3]) <= int(match[2]) + 399:
                raise Closed("Requested excerpt must contain at most 400 ordered lines")
            if path not in tree:
                result[query] = {"missing": True}
                continue
            size = int(self.text("cat-file", "-s", tree[path][1]))
            if not match and used + size > maximum:
                result[query] = {"omitted": True, "bytes": size, "git_blob": tree[path][1]}
                continue
            data = self.read(revision, path)
            try:
                content = data.decode()
            except UnicodeDecodeError:
                result[query] = {"binary": True, "sha256": digest(data)}
            else:
                info = {"sha256": digest(data)}
                if match:
                    lines = content.splitlines(keepends=True)
                    start, end = int(match[2]), int(match[3])
                    content = "".join(lines[start - 1:end])
                    info["excerpt"] = {"start": start, "end": min(end, len(lines)), "total_lines": len(lines)}
                if used + len(content.encode()) > maximum:
                    info.update(omitted=True, bytes=len(content.encode()))
                else:
                    info["content"] = content
                    used += len(content.encode())
                result[query] = info
        return result

    def search(self, revision, terms):
        results = {}
        for term in terms:
            if not isinstance(term, str) or not 1 <= len(term) <= 200 or "\n" in term or "\0" in term:
                raise Closed("Search terms must be bounded literal single-line strings")
            observed = self.command("grep", "-n", "-I", "-F", "-e", term, sha(revision), "--", check=False)
            if observed.returncode not in (0, 1):
                raise Closed("Source search failed")
            hits = []
            for line in observed.stdout.decode().splitlines():
                match = re.match(r"[0-9a-f]{40}:(.+?):([0-9]+):", line)
                if match:
                    path, number = safe_path(match[1]), int(match[2])
                    if path not in [row["path"] for row in hits]:
                        hits.append({"path": path, "excerpt": f"{path}#L{max(1, number-12)}-L{number+24}"})
            results[term] = {"matches": hits[:24], "total_files": len(hits), "truncated": len(hits) > 24}
        return results

    @contextlib.contextmanager
    def snapshot(self, revision):
        with tempfile.TemporaryDirectory(prefix="agent-product-") as directory:
            root = Path(directory)
            total = 0
            for path, (mode, blob) in self.tree(revision).items():
                size = int(self.text("cat-file", "-s", blob))
                total += size
                if size > 8_000_000 or total > 256_000_000:
                    raise Closed("Snapshot exceeds declared size limits")
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self.command("cat-file", "blob", blob, limit=8_000_001).stdout)
                target.chmod(0o755 if mode == "100755" else 0o644)
            yield root

    def commit(self, parent, edits, effect, *, allowed, protected, working_set=None, additions_only=False, maximum=1_000_000):
        if not edits or len({row["path"] for row in edits}) != len(edits):
            raise Closed("Edits must be nonempty and unique")
        if sum(len(row["content"].encode()) for row in edits) > maximum:
            raise Closed("Edit byte limit exceeded")
        tree = self.tree(parent)
        for row in edits:
            path = row["path"]
            if not path_allowed(path, allowed, protected, [".github/*", ".agent-control/*", "AGENTS.md"]):
                raise Closed("Edit exceeds path authority: " + path)
            if working_set is not None and path not in working_set:
                raise Closed("Edit exceeds architect working set: " + path)
            old = self.read(parent, path)
            if additions_only and (old is not None or row["delete"]):
                raise Closed("Independent tester may only add new files")
            if (digest(old) if old is not None else "") != row["expected_sha256"]:
                raise Closed("Edit does not name the current source hash: " + path)
            if (row["delete"] and old is None) or (not row["delete"] and old == row["content"].encode()):
                raise Closed("No-op edit")
        with tempfile.TemporaryDirectory(prefix="agent-index-") as temporary:
            env = {"GIT_INDEX_FILE": str(Path(temporary) / "index")}
            self.text("read-tree", sha(parent), env=env)
            for row in edits:
                path = row["path"]
                if row["delete"]:
                    self.text("update-index", "--force-remove", "--", path, env=env)
                else:
                    blob = self.text("hash-object", "-w", "--stdin", data=row["content"].encode())
                    mode = tree.get(path, ("100644", ""))[0]
                    self.text("update-index", "--add", "--cacheinfo", mode, blob, path, env=env)
            candidate_tree = self.text("write-tree", env=env)
        return self._commit_tree(candidate_tree, [parent], effect)

    def _commit_tree(self, tree, parents, effect):
        env = {"GIT_AUTHOR_NAME": "Agent Control", "GIT_AUTHOR_EMAIL": "agent-control@localhost",
               "GIT_COMMITTER_NAME": "Agent Control", "GIT_COMMITTER_EMAIL": "agent-control@localhost",
               "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"}
        args = ["commit-tree", tree]
        for parent in parents:
            args += ["-p", sha(parent)]
        commit = sha(self.text(*args, env=env, data=f"Controlled delivery\n\nAgent-Effect: {effect}\n".encode()))
        # Receipts may outlive reflogs. Retain negative controls and intermediate
        # commits as well as published candidates, including before receipt save.
        self.text("update-ref", "refs/agent-effects/" + digest(effect.encode()), commit)
        return commit

    def changed(self, base, head):
        return [safe_path(x.decode()) for x in self.command("diff", "--name-only", "-z", sha(base), sha(head)).stdout.split(b"\0") if x]

    def parents(self, commit):
        return self.text("show", "-s", "--format=%P", sha(commit)).split()

    def merge_local(self, base, head, effect):
        current = self.resolve(self.branch)
        if current != base:
            require_merge_identity(base, head, self.parents(current))
            if f"Agent-Effect: {effect}" not in self.text("show", "-s", "--format=%B", current).splitlines():
                raise Closed("Base moved to an unrelated merge")
            return current
        self.text("merge-base", "--is-ancestor", sha(base), sha(head))
        merge = self._commit_tree(self.text("rev-parse", head + "^{tree}"), [base, head], effect)
        self.text("update-ref", "refs/heads/" + self.branch, merge, base)
        require_merge_identity(base, head, self.parents(merge))
        return merge

    def refresh_base(self, head, base, effect):
        # merge-tree writes objects without a checkout, hooks or user merge drivers.
        result = self.command("merge-tree", "--write-tree", sha(head), sha(base), check=False)
        if result.returncode:
            raise Closed("Base refresh has conflicts; no file was overwritten")
        tree = sha(result.stdout.decode().splitlines()[0])
        return self._commit_tree(tree, [head, base], effect)

    def publish_branch(self, branch, head):
        self.text("check-ref-format", "refs/heads/" + branch)
        self.text("update-ref", "refs/heads/" + branch, sha(head))
        self.text("push", "origin", "refs/heads/" + branch + ":refs/heads/" + branch)

    def fetch_merge(self, revision):
        self.text("fetch", "--no-tags", "origin", sha(revision))
        return self.resolve(revision)
