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


def verify_release(source: Path, commit: str) -> dict:
    manifest_path = source / "RELEASE-MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("version") != COMPAT["flowai_control"]["version"]:
        raise SystemExit("FlowAI-Control release version does not match COMPATIBILITY.json")
    expected = set(manifest.get("files", {})) | {"RELEASE-MANIFEST.json"}
    tracked = set(filter(None, call(
        ["git", "ls-tree", "-r", "--name-only", commit], cwd=source, capture=True
    ).splitlines()))
    if tracked != expected:
        raise SystemExit(
            "controller release manifest and exact Git tree differ; "
            f"missing={sorted(expected-tracked)[:10]} extra={sorted(tracked-expected)[:10]}"
        )
    for relative, digest in manifest["files"].items():
        path = source / relative
        if not path.is_file() or path.is_symlink() or sha256(path) != digest:
            raise SystemExit(f"release integrity failure: {relative}")
    return manifest


def verify_installed_release(destination: Path, manifest: dict) -> None:
    expected = set(manifest["files"]) | {"RELEASE-MANIFEST.json"}
    actual = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != expected:
        raise SystemExit(
            "installed runtime file set differs from pinned release; "
            f"missing={sorted(expected-actual)[:10]} extra={sorted(actual-expected)[:10]}"
        )
    if json.loads((destination / "RELEASE-MANIFEST.json").read_text()) != manifest:
        raise SystemExit("installed runtime manifest differs from pinned release")
    for relative, digest in manifest["files"].items():
        path = destination / relative
        if not path.is_file() or path.is_symlink() or sha256(path) != digest:
            raise SystemExit(f"installed runtime differs from pinned release: {relative}")


def install_release(source: Path, destination: Path, manifest: dict) -> None:
    if destination.exists():
        verify_installed_release(destination, manifest)
        return
    staging = destination.with_name(destination.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for relative in sorted(manifest["files"]):
        src = source / relative
        dst = staging / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    shutil.copy2(source / "RELEASE-MANIFEST.json", staging / "RELEASE-MANIFEST.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, destination)
    verify_installed_release(destination, manifest)


def repository_preflight(policy: dict) -> None:
    control = policy.get("control_repo")
    product = policy.get("product_repo")
    if not isinstance(control, str) or not isinstance(product, str):
        raise SystemExit("policy is missing product_repo/control_repo")
    if control.casefold() == product.casefold():
        raise SystemExit("product_repo and control_repo must be different")
    allowed_permissions = {"ADMIN", "MAINTAIN", "WRITE"}
    for role, repo in (("control", control), ("product", product)):
        raw = call([
            "gh", "repo", "view", repo, "--json",
            "nameWithOwner,isPrivate,hasIssuesEnabled,viewerPermission,defaultBranchRef"
        ], capture=True)
        info = json.loads(raw)
        if info.get("viewerPermission") not in allowed_permissions:
            raise SystemExit(f"{role} repository requires write permission: {repo}")
        branch = (info.get("defaultBranchRef") or {}).get("name")
        if branch != "main":
            raise SystemExit(f"{role} repository default branch must be main: {repo} -> {branch!r}")
        if role == "control":
            if info.get("isPrivate") is not True:
                raise SystemExit("control repository must be private")
            if info.get("hasIssuesEnabled") is not True:
                raise SystemExit("control repository must have GitHub Issues enabled")
        call(["git", "ls-remote", f"https://github.com/{repo}.git", "HEAD"], capture=True)

    issue = policy.get("command_issue")
    if type(issue) is not int or issue < 1:
        raise SystemExit("policy command_issue must be a positive integer")
    raw = call([
        "gh", "issue", "view", str(issue), "--repo", control,
        "--json", "number,state,title"
    ], capture=True)
    value = json.loads(raw)
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
Description=FlowAI-Control reference controller
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


def write_unit(text: str, replace: bool) -> Path:
    unit = Path.home() / ".config" / "systemd" / "user" / "flow-loop.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    if unit.exists():
        current = unit.read_text()
        if current == text:
            return unit
        if not replace:
            raise SystemExit(
                f"{unit} already exists with different content. Re-run only after review with --replace-unit."
            )
    temp = unit.with_suffix(".service.tmp")
    temp.write_text(text)
    temp.chmod(0o600)
    os.replace(temp, unit)
    return unit


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install the pinned FlowAI-Control runtime while keeping source, control state and product separate."
    )
    ap.add_argument("--policy", type=Path, default=Path("policy.json"))
    ap.add_argument("--work", type=Path, default=Path.home() / ".local/state/flow-loop")
    ap.add_argument("--replace-unit", action="store_true")
    ap.add_argument("--skip-engine-tests", action="store_true")
    ap.add_argument("--skip-codex-smoke", action="store_true")
    ap.add_argument("--skip-product-baseline", action="store_true")
    a = ap.parse_args()

    if os.geteuid() == 0:
        raise SystemExit("run as the dedicated unprivileged controller user, never root")
    for command in ("git", "gh", "python3", "podman", "codex", "systemctl"):
        if shutil.which(command) is None:
            raise SystemExit(f"missing required executable: {command}")

    policy = a.policy.expanduser().resolve()
    if not policy.is_file() or policy.is_symlink():
        raise SystemExit(f"missing regular policy file: {policy}")
    policy_data = json.loads(policy.read_text())
    repository_preflight(policy_data)
    compatibility = COMPAT["flowai_control"]
    commit = compatibility["commit"]
    if not SHA.fullmatch(commit):
        raise SystemExit("invalid pinned controller SHA in COMPATIBILITY.json")

    with tempfile.TemporaryDirectory(prefix="flowai-control-source-") as d:
        source = Path(d) / "source"
        call(["gh", "repo", "clone", compatibility["repository"], str(source), "--", "--no-checkout"])
        call(["git", "fetch", "--quiet", "origin", commit], cwd=source)
        call(["git", "checkout", "--quiet", "--detach", commit], cwd=source)
        head = call(["git", "rev-parse", "HEAD"], cwd=source, capture=True)
        if head != commit:
            raise SystemExit("fetched controller source is not the pinned commit")
        manifest = verify_release(source, commit)
        runtime = Path.home() / ".local" / "share" / "flow-loop" / f"{compatibility['version']}-{commit}"
        install_release(source, runtime, manifest)

    work = a.work.expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)

    if not a.skip_engine_tests:
        call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=runtime)
    call([sys.executable, "-m", "flow_loop", "doctor", "--config", str(policy), "--work", str(work)], cwd=runtime)
    if not a.skip_codex_smoke:
        call([sys.executable, "scripts/smoke_codex.py", "--config", str(policy)], cwd=runtime)
    if not a.skip_product_baseline:
        call([sys.executable, "scripts/verify_product.py", "--config", str(policy), "--work", str(work)], cwd=runtime)

    fingerprint = call(
        [sys.executable, "-m", "flow_loop", "fingerprint", "--config", str(policy), "--work", str(work)],
        cwd=runtime, capture=True
    )
    unit = write_unit(unit_text(runtime, policy, work), a.replace_unit)
    call(["systemctl", "--user", "daemon-reload"])
    call(["systemctl", "--user", "enable", "--now", unit.name])
    call(["systemctl", "--user", "is-active", "--quiet", unit.name])

    print(json.dumps({
        "runtime_source": compatibility["repository"],
        "runtime_commit": commit,
        "runtime": str(runtime),
        "policy": str(policy),
        "work": str(work),
        "service": unit.name,
        "fingerprint": fingerprint,
        "activation_command": f"/loop activate {fingerprint}",
        "next": "Post the activation command as a new one-line owner comment in the command issue, then create a Flow Loop goal issue."
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
