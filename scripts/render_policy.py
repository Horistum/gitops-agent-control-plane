#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
OWNER = re.compile(r"[A-Za-z0-9_.-]+")
CONTROLLER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
IMAGE = re.compile(r"(?:[A-Za-z0-9./:_-]+@)?sha256:[0-9a-f]{64}")


def fail(message: str) -> None:
    raise SystemExit("render-policy: " + message)


def atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        fail(f"{path} already exists; refusing to overwrite an authority policy")
    fd, temp_name = tempfile.mkstemp(prefix=".policy-", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Render a tenant policy from the reviewed reference template.")
    p.add_argument("--product-repo", required=True)
    p.add_argument("--control-repo", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--command-issue", required=True, type=int)
    p.add_argument("--controller-id", default="reference-loop-primary")
    p.add_argument("--test-image", required=True,
                   help="Locally preloaded immutable image, e.g. repo/image@sha256:<64 hex>")
    p.add_argument("--codex-version", required=True,
                   help="Exact output of: codex --version")
    p.add_argument("--codex-home", default=str(Path.home() / ".codex-loop"))
    p.add_argument("--model", default="", help="Optional Codex model override; empty uses Codex default.")
    p.add_argument("--check-name", default="flowai-reference-ci")
    p.add_argument("--check-app-id", type=int, default=15368)
    p.add_argument("--goal-pattern", action="append", dest="goal_patterns")
    p.add_argument("--output", type=Path, default=Path("policy.json"))
    a = p.parse_args()

    for label, value in (("product repository", a.product_repo), ("control repository", a.control_repo)):
        if not REPO.fullmatch(value):
            fail(f"invalid {label}: {value!r}; expected OWNER/NAME")
    if a.product_repo.casefold() == a.control_repo.casefold():
        fail("product_repo and control_repo must be different repositories")
    if not OWNER.fullmatch(a.owner):
        fail("owner login contains unsupported characters")
    if a.command_issue < 1:
        fail("--command-issue must be positive")
    if not CONTROLLER.fullmatch(a.controller_id):
        fail("invalid --controller-id")
    if not IMAGE.fullmatch(a.test_image) or a.test_image.endswith("0" * 64):
        fail("--test-image must be a non-zero SHA-256 pinned image reference")
    if not a.codex_version.strip():
        fail("--codex-version must not be empty")
    if not a.check_name.strip() or a.check_app_id < 1:
        fail("required check name/app id must be explicit")
    patterns = a.goal_patterns or ["DEMO-*"]
    if len(patterns) > 20 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_*-]{0,79}", x) for x in patterns):
        fail("invalid --goal-pattern")

    template = json.loads((ROOT / "config" / "policy.template.json").read_text(encoding="utf-8"))
    template.update(
        product_repo=a.product_repo,
        control_repo=a.control_repo,
        controller_id=a.controller_id,
        owners=[a.owner],
        command_issue=a.command_issue,
        test_image=a.test_image,
        codex_version=a.codex_version.strip(),
        codex_home=str(Path(a.codex_home).expanduser().resolve()),
    )
    template["required_checks"] = [{"name": a.check_name, "app_id": a.check_app_id}]
    template["postmerge_checks"] = [{"name": a.check_name, "app_id": a.check_app_id}]
    template["github_goals"]["allowed_item_patterns"] = patterns
    template["models"] = {"default": a.model} if a.model else {}

    output = a.output.expanduser().resolve()
    atomic_write(output, json.dumps(template, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "policy": str(output),
        "product_repo": a.product_repo,
        "control_repo": a.control_repo,
        "command_issue": a.command_issue,
        "test_image": a.test_image,
        "codex_version": a.codex_version.strip(),
        "model_override": a.model or None,
        "next": "Run scripts/install_runtime.py --policy <policy> after product CI/governance and ChatGPT Codex login are ready."
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
