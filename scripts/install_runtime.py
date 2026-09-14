#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMPAT = json.loads((ROOT / "COMPATIBILITY.json").read_text())
SHA = re.compile(r"[0-9a-f]{40}")


def call(argv: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    print("$ " + " ".join(argv), flush=True)
    p = subprocess.run(argv, cwd=cwd, text=True, capture_output=capture)
    if p.returncode:
        detail = (p.stderr or p.stdout or "")[-4000:]
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(argv)}\n{detail}")
    return p.stdout.strip() if capture else ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def expected_files(manifest: dict) -> set[str]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise SystemExit("runtime release manifest has no file map")
    return set(files) | {"RELEASE-MANIFEST.json"}


def verify_release(source: Path, commit: str, runtime: dict) -> dict:
    manifest_path = source / "RELEASE-MANIFEST.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise SystemExit("runtime release manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("version") != runtime["version"]:
        raise SystemExit("runtime release version does not match COMPATIBILITY.json")
    expected = expected_files(manifest)
    tracked = set(filter(None, call(
        ["git", "ls-tree", "-r", "--name-only", commit], cwd=source, capture=True
    ).splitlines()))
    if tracked != expected:
        raise SystemExit(
            "runtime manifest and exact Git tree differ; "
            f"missing={sorted(tracked-expected)[:10]} unexpected={sorted(expected-tracked)[:10]}"
        )
    for relative, digest in manifest["files"].items():
        path = source / relative
        if not path.is_file() or path.is_symlink() or sha256(path) != digest:
            raise SystemExit(f"runtime release integrity failure: {relative}")
    return manifest


def actual_runtime_files(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix() for p in root.rglob("*")
        if (p.is_file() or p.is_symlink()) and "__pycache__" not in p.parts and not p.name.endswith((".pyc", ".pyo"))
    }


def verify_installed(destination: Path, manifest: dict) -> None:
    expected = expected_files(manifest)
    actual = actual_runtime_files(destination)
    if actual != expected:
        raise SystemExit(
            "installed runtime file set differs from pinned release; "
            f"missing={sorted(expected-actual)[:10]} unexpected={sorted(actual-expected)[:10]}"
        )
    for relative, digest in manifest["files"].items():
        path = destination / relative
        if not path.is_file() or path.is_symlink() or sha256(path) != digest:
            raise SystemExit(f"installed runtime differs from pinned release: {relative}")


def install_release(source: Path, destination: Path, manifest: dict) -> None:
    if destination.exists():
        verify_installed(destination, manifest)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=destination.name + ".staging-", dir=destination.parent))
    try:
        for relative in sorted(manifest["files"]):
            src = source / relative
            dst = staging / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        shutil.copy2(source / "RELEASE-MANIFEST.json", staging / "RELEASE-MANIFEST.json")
        verify_installed(staging, manifest)
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def repository_preflight(policy: dict) -> None:
    control = policy.get("control_repo")
    product = policy.get("product_repo")
    if not isinstance(control, str) or not isinstance(product, str) or control.casefold() == product.casefold():
        raise SystemExit("policy must contain distinct product_repo and control_repo")
    writable = {"ADMIN", "MAINTAIN", "WRITE"}
    for role, repo in (("control", control), ("product", product)):
        info = json.loads(call([
            "gh", "repo", "view", repo, "--json",
            "nameWithOwner,isPrivate,hasIssuesEnabled,viewerPermission,defaultBranchRef"
        ], capture=True))
        if info.get("viewerPermission") not in writable:
            raise SystemExit(f"{role} repository requires write permission: {repo}")
        branch = (info.get("defaultBranchRef") or {}).get("name")
        if branch != "main":
            raise SystemExit(f"{role} repository default branch must be main: {repo} -> {branch!r}")
        if role == "control" and (info.get("isPrivate") is not True or info.get("hasIssuesEnabled") is not True):
            raise SystemExit("control repository must be private with Issues enabled")
        call(["git", "ls-remote", f"https://github.com/{repo}.git", "HEAD"], capture=True)

    issue = policy.get("command_issue")
    if type(issue) is not int or issue < 1:
        raise SystemExit("policy command_issue must be a positive integer")
    value = json.loads(call([
        "gh", "issue", "view", str(issue), "--repo", control, "--json", "number,state,title"
    ], capture=True))
    if value.get("state") != "OPEN":
        raise SystemExit(f"command issue #{issue} is not open in {control}")


def unit_text(runtime: Path, policy: Path, work: Path) -> str:
    for value in (runtime, policy, work):
        if any(c.isspace() for c in str(value)):
            raise SystemExit("reference installer currently requires paths without whitespace")
    python = shutil.which("python3")
    if not python:
        raise SystemExit("python3 not found")
    path = ":".join([str(Path.home() / ".local/bin"), "/usr/local/bin", "/usr/bin", "/bin"])
    return f"""[Unit]
Description=GitOps Agent Control Plane reference controller
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=3

[Service]
Type=simple
WorkingDirectory={runtime}
Environment=PYTHONUNBUFFERED=1
Environment=PATH={path}
ExecStart={python} -m flow_loop run --config {policy} --work {work}
Restart=on-failure
RestartSec=15
NoNewPrivileges=yes

[Install]
WantedBy=default.target
"""


def write_unit(text: str, name: str, replace: bool) -> Path:
    unit = Path.home() / ".config" / "systemd" / "user" / name
    unit.parent.mkdir(parents=True, exist_ok=True)
    if unit.exists():
        current = unit.read_text()
        if current == text:
            return unit
        if not replace:
            raise SystemExit(f"{unit} already exists with different content; use --replace-unit only after review")
    temp = unit.with_suffix(unit.suffix + ".tmp")
    temp.write_text(text)
    temp.chmod(0o600)
    os.replace(temp, unit)
    return unit


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install and prove the pinned runtime adapter.")
    ap.add_argument("--policy", type=Path, default=Path("policy.json"))
    ap.add_argument("--work", type=Path, default=Path.home() / ".local/state/agent-control-plane")
    ap.add_argument("--replace-unit", action="store_true")
    ap.add_argument("--skip-engine-tests", action="store_true")
    ap.add_argument("--skip-model-smoke", action="store_true")
    ap.add_argument("--skip-product-baseline", action="store_true")
    a = ap.parse_args(argv)

    if os.geteuid() == 0:
        raise SystemExit("run as a dedicated unprivileged controller user, never root")
    for command in ("git", "gh", "python3", "podman", "codex", "systemctl"):
        if shutil.which(command) is None:
            raise SystemExit(f"missing required executable: {command}")

    policy = a.policy.expanduser().resolve()
    if not policy.is_file() or policy.is_symlink():
        raise SystemExit(f"missing regular policy file: {policy}")
    policy_data = json.loads(policy.read_text())
    repository_preflight(policy_data)

    runtime_cfg = COMPAT["runtime_adapter"]
    commit = runtime_cfg["commit"]
    if not SHA.fullmatch(commit):
        raise SystemExit("invalid pinned runtime SHA in COMPATIBILITY.json")

    with tempfile.TemporaryDirectory(prefix="agent-runtime-source-") as d:
        source = Path(d) / "source"
        call(["gh", "repo", "clone", runtime_cfg["repository"], str(source), "--", "--no-checkout"])
        call(["git", "fetch", "--quiet", "origin", commit], cwd=source)
        call(["git", "checkout", "--quiet", "--detach", commit], cwd=source)
        if call(["git", "rev-parse", "HEAD"], cwd=source, capture=True) != commit:
            raise SystemExit("fetched runtime source is not the pinned commit")
        manifest = verify_release(source, commit, runtime_cfg)
        runtime = Path.home() / ".local/share/agent-control-plane" / f"{runtime_cfg['version']}-{commit}"
        install_release(source, runtime, manifest)

    work = a.work.expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not a.skip_engine_tests:
        call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=runtime)
    call([sys.executable, "-m", "flow_loop", "doctor", "--config", str(policy), "--work", str(work)], cwd=runtime)
    if not a.skip_model_smoke:
        call([sys.executable, "scripts/smoke_codex.py", "--config", str(policy)], cwd=runtime)
    if not a.skip_product_baseline:
        call([sys.executable, "scripts/verify_product.py", "--config", str(policy), "--work", str(work)], cwd=runtime)

    fingerprint = call([sys.executable, "-m", "flow_loop", "fingerprint", "--config", str(policy), "--work", str(work)], cwd=runtime, capture=True)
    unit = write_unit(unit_text(runtime, policy, work), runtime_cfg["service_name"], a.replace_unit)
    call(["systemctl", "--user", "daemon-reload"])
    call(["systemctl", "--user", "enable", "--now", unit.name])
    call(["systemctl", "--user", "is-active", "--quiet", unit.name])

    print(json.dumps({
        "runtime_repository": runtime_cfg["repository"],
        "runtime_commit": commit,
        "runtime": str(runtime),
        "policy": str(policy),
        "work": str(work),
        "service": unit.name,
        "fingerprint": fingerprint,
        "next": f"python3 scripts/control.py --policy {policy} activate --fingerprint {fingerprint}"
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
