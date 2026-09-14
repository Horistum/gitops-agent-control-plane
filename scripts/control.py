#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def backend_command(args: argparse.Namespace) -> str:
    cmd = args.command
    if cmd in {"refresh", "pause", "drain", "resume"}:
        return f"/loop {cmd}"
    if cmd == "activate":
        return f"/loop activate {args.fingerprint}"
    if cmd == "retry":
        return f"/loop retry {args.task}"
    if cmd in {"approve", "replan"}:
        return f"/loop {cmd} {args.task} {args.hash}"
    if cmd == "cancel-goal":
        return f"/loop cancel-goal {args.goal} {args.hash}"
    raise ValueError(f"unsupported command: {cmd}")


def post(repo: str, issue: int, body: str) -> dict:
    p = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{issue}/comments", "-X", "POST", "--input", "-"],
        input=json.dumps({"body": body}), text=True, capture_output=True
    )
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return json.loads(p.stdout)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Portable owner control surface for the active runtime adapter.")
    p.add_argument("--policy", type=Path, default=Path("policy.json"))
    p.add_argument("--dry-run", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("refresh", "pause", "drain", "resume"):
        sub.add_parser(name)
    a = sub.add_parser("activate"); a.add_argument("--fingerprint", required=True)
    r = sub.add_parser("retry"); r.add_argument("--task", required=True)
    for name in ("approve", "replan"):
        q = sub.add_parser(name); q.add_argument("--task", required=True); q.add_argument("--hash", required=True)
    c = sub.add_parser("cancel-goal"); c.add_argument("--goal", required=True); c.add_argument("--hash", required=True)
    return p


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    policy = json.loads(a.policy.read_text())
    body = backend_command(a)
    if "\n" in body or len(body) > 240:
        raise SystemExit("adapter produced an invalid command")
    if a.dry_run:
        print(json.dumps({"repo": policy["control_repo"], "issue": policy["command_issue"], "command": body}, indent=2))
        return 0
    value = post(policy["control_repo"], policy["command_issue"], body)
    print(json.dumps({"comment_id": value.get("id"), "url": value.get("html_url")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
