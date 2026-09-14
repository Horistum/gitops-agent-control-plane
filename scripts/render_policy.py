#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "policy.template.json"
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
IMAGE = re.compile(r"(?:[A-Za-z0-9./:_-]+@)?sha256:[0-9a-f]{64}")


def render(args: argparse.Namespace) -> dict:
    value = json.loads(TEMPLATE.read_text())
    if not REPO.fullmatch(args.product_repo) or not REPO.fullmatch(args.control_repo):
        raise ValueError("repositories must use owner/name form")
    if args.product_repo.casefold() == args.control_repo.casefold():
        raise ValueError("product and control repositories must be different")
    if not IMAGE.fullmatch(args.test_image):
        raise ValueError("test image must be pinned by sha256 digest")
    if not args.owner.strip() or args.command_issue < 1 or not args.controller_id.strip():
        raise ValueError("owner, command issue and controller id are required")
    if not args.codex_version.strip():
        raise ValueError("exact runtime model CLI version is required")

    value.update(
        product_repo=args.product_repo,
        control_repo=args.control_repo,
        controller_id=args.controller_id,
        owners=[args.owner],
        command_issue=args.command_issue,
        test_image=args.test_image,
        codex_home=str(Path(args.codex_home).expanduser()),
        codex_version=args.codex_version,
        models={} if not args.model else {"default": args.model},
    )
    patterns = args.goal_patterns or ["EXAMPLE-*"]
    value["github_goals"]["allowed_item_patterns"] = patterns
    value["required_checks"] = [{"name": args.check_name, "app_id": args.check_app_id}]
    value["postmerge_checks"] = [{"name": args.check_name, "app_id": args.check_app_id}]
    value["auto_merge"] = args.auto_merge_through != "none"
    value["github_goals"]["max_auto_merge_risk"] = args.auto_merge_through
    return value


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Render a tenant policy from the portable reference template.")
    p.add_argument("--product-repo", required=True)
    p.add_argument("--control-repo", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--command-issue", required=True, type=int)
    p.add_argument("--controller-id", required=True)
    p.add_argument("--test-image", required=True)
    p.add_argument("--codex-version", required=True)
    p.add_argument("--codex-home", default=str(Path.home() / ".codex-loop"))
    p.add_argument("--model", default="")
    p.add_argument("--check-name", default="agent-control-reference-ci")
    p.add_argument("--check-app-id", type=int, default=15368)
    p.add_argument("--goal-pattern", dest="goal_patterns", action="append")
    p.add_argument("--auto-merge-through", choices=("none", "low", "medium"), default="medium")
    p.add_argument("--output", type=Path, default=Path("policy.json"))
    return p


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    value = render(a)
    out = a.output.expanduser().resolve()
    if out.exists():
        raise SystemExit(f"refusing to overwrite existing policy: {out}")
    out.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    out.chmod(0o600)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
