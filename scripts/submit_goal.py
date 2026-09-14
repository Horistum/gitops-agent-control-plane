#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

# Backend protocol constants are intentionally isolated in this adapter.
GOAL_MARKER = "<!-- flow-loop-goal:v1 -->"
TITLE_PREFIX = "[Flow Loop Goal]"


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("goal file must contain one JSON object")
    return value


def validate_goal(value: dict) -> dict:
    expected = {"objective", "items", "risk_ceiling", "auto_merge", "success_condition", "forbidden_directions"}
    if set(value) != expected:
        raise ValueError(f"goal fields mismatch: missing={sorted(expected-set(value))} unexpected={sorted(set(value)-expected)}")
    if not isinstance(value["items"], list) or not value["items"] or not all(isinstance(x, str) and x for x in value["items"]):
        raise ValueError("items must be a non-empty string list")
    if value["risk_ceiling"] not in ("low", "medium", "high"):
        raise ValueError("risk_ceiling must be low, medium or high")
    if value["auto_merge"] not in ("none", "low", "medium"):
        raise ValueError("auto_merge must be none, low or medium")
    for key in ("objective", "success_condition", "forbidden_directions"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"{key} must be a non-empty string")
    return value


def backend_issue(goal: dict) -> tuple[str, str]:
    goal = validate_goal(goal)
    risk = goal["risk_ceiling"].upper()
    merge = {"none":"Vypnuto", "low":"Jen LOW", "medium":"LOW a MEDIUM"}[goal["auto_merge"]]
    items = "\n".join(goal["items"])
    body = f"""{GOAL_MARKER}

### Cíl
{goal['objective'].strip()}

### Položky roadmapy
{items}

### Nejvyšší přijatelné riziko
{risk}

### Automatický merge
{merge}

### Podmínka dokončení
{goal['success_condition'].strip()}

### Zakázané směry
{goal['forbidden_directions'].strip()}

### Potvrzení
- [x] Rozumím, že Goal Issue schvaluje pouze uvedený rozsah a nikdy neobchází hard safety gates.
"""
    title = f"{TITLE_PREFIX} {', '.join(goal['items'])}"
    return title, body


def create_issue(repo: str, title: str, body: str) -> dict:
    p = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues", "-X", "POST", "--input", "-"],
        input=json.dumps({"title": title, "body": body}), text=True, capture_output=True
    )
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return json.loads(p.stdout)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Submit a portable engineering goal through the configured runtime adapter.")
    p.add_argument("--policy", type=Path, default=Path("policy.json"))
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    policy = json.loads(a.policy.read_text())
    goal = validate_goal(read_json(a.file))
    title, body = backend_issue(goal)
    if a.dry_run:
        print(json.dumps({"repo": policy["control_repo"], "title": title, "body": body}, indent=2, ensure_ascii=False))
        return 0
    issue = create_issue(policy["control_repo"], title, body)
    print(json.dumps({"number": issue.get("number"), "url": issue.get("html_url"), "items": goal["items"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
