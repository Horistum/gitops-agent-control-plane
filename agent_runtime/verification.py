"""Execute immutable snapshots; independently observe process and JUnit results."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import uuid
import xml.etree.ElementTree as ET
from control_plane_core import evaluate_predicates
from .io import Closed, digest, isolated_environment, loads, run


def junit(root, patterns):
    files = set()
    for pattern in patterns:
        if pattern.startswith("/") or ".." in pattern.split("/"):
            raise Closed("Unsafe JUnit selector")
        files.update(root.glob(pattern))
    executed, failures, errors, skipped, identities = set(), set(), set(), set(), set()
    details = {}
    if len(files) > 2048:
        raise Closed("Too many JUnit reports")
    for path in sorted(files):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise Closed("JUnit report is not a regular snapshot file")
        if path.stat().st_size > 8_000_000:
            raise Closed("JUnit report exceeds byte limit")
        data = path.read_bytes()
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise Closed("DTD/entity in JUnit report")
        try:
            document = ET.fromstring(data)
        except ET.ParseError as exc:
            raise Closed("Malformed JUnit report") from exc
        for case in document.iter("testcase"):
            name, classname = case.get("name"), case.get("classname")
            if not name or not classname:
                raise Closed("JUnit lacks stable class:name identity")
            identity = classname + ":" + name
            if identity in identities:
                raise Closed("Duplicate JUnit test identity")
            identities.add(identity)
            if case.find("skipped") is not None:
                skipped.add(identity)
                continue
            executed.add(identity)
            if case.find("failure") is not None:
                failures.add(identity)
            if case.find("error") is not None:
                errors.add(identity)
            if identity in failures | errors and len(details) < 128:
                details[identity] = "".join(case.itertext())[-1000:]
    return {"executed_identities": sorted(executed), "failed_identities": sorted(failures),
            "error_identities": sorted(errors), "skipped_identities": sorted(skipped),
            "assertion_failures": len(failures), "errors": len(errors), "details": details}


class Verification:
    def __init__(self, configuration):
        self.config = configuration

    def preflight(self):
        if self.config["kind"] == "trusted-local":
            return {"kind": "trusted-local", "isolated": False}
        result = run(["podman", "info", "--format", "json"], limit=200_000)
        host = loads(result.stdout).get("host", {})
        if host.get("security", {}).get("rootless") is not True or host.get("serviceIsRemote") is True:
            raise Closed("Execution requires rootless Podman")
        if (host.get("cgroupVersion") != "v2" or host.get("cgroupManager") != "systemd"
                or not {"cpu", "memory", "pids"} <= set(host.get("cgroupControllers", []))):
            raise Closed("Rootless resource limits require cgroup v2/systemd with delegated cpu, memory and pids controllers")
        run(["podman", "image", "exists", self.config["image"]])
        return {"kind": "podman", "rootless": True, "resource_limits": "delegated", "image": self.config["image"]}

    def command(self, argv, root):
        if self.config["kind"] == "trusted-local":
            with tempfile.TemporaryDirectory(prefix="agent-test-home-") as home:
                return run(argv, cwd=root, env=isolated_environment(home), timeout=self.config["timeout"], check=False)
        name = "agent-test-" + uuid.uuid4().hex
        args = ["podman", "run", "--rm", "--pull=never", "--name", name,
                "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--userns=keep-id", "--user", f"{os.getuid()}:{os.getgid()}",
                "--pids-limit=256", "--memory", str(self.config["memory_mb"]) + "m",
                "--cpus", str(self.config["cpus"]), "--tmpfs", "/tmp:rw,size=256m",
                "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--workdir", "/workspace", "--volume", str(root) + ":/workspace:rw,Z",
                "--entrypoint", argv[0], self.config["image"], *argv[1:]]
        try:
            return run(args, timeout=self.config["timeout"], check=False)
        finally:
            # A timed-out client must not leave a worker running with the mount.
            run(["podman", "rm", "--force", "--ignore", name], timeout=30, check=False)

    def observe(self, repo, head, base, spec_hash, *, cases=False):
        outputs, cli = [], {}
        with repo.snapshot(head) as root:
            # Never accept tracked/stale XML as the result of this execution.
            for pattern in self.config["junit"]:
                if pattern.startswith("/") or ".." in pattern.split("/"):
                    raise Closed("Unsafe JUnit selector")
                for path in root.glob(pattern):
                    if not path.is_file() or path.is_symlink():
                        raise Closed("Invalid existing JUnit report")
                    path.unlink()
            for argv in self.config["commands"]:
                result = self.command(argv, root)
                outputs.append({"argv": argv, "exit_code": result.returncode,
                                "stdout_hash": digest(result.stdout), "stderr_hash": digest(result.stderr),
                                "diagnostic": result.stdout.decode(errors="replace")[-2000:],
                                "stderr_diagnostic": result.stderr.decode(errors="replace")[-2000:]})
            tests = junit(root, self.config["junit"])
        # Each external assertion starts with a fresh exact snapshot, so a build
        # cannot silently rewrite the product used by the subsequent CLI gate.
        if cases:
            for case in self.config["cases"]:
                with repo.snapshot(head) as root:
                    result = self.command(case["argv"], root)
                    observation = {"exit_code": result.returncode, "stdout": result.stdout.decode(errors="replace")}
                    cli[case["id"]] = evaluate_predicates(case["predicates"], observation)
        passed = (all(row["exit_code"] == 0 for row in outputs)
                  and len(tests["executed_identities"]) >= self.config["min_tests"]
                  and not tests["failed_identities"] and not tests["error_identities"]
                  and all(row["passed"] for row in cli.values()))
        return {"head": head, "base": base, "spec_hash": spec_hash, "passed": passed,
                "junit": tests, "commands": outputs, "cli": cli}
