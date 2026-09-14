#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

RULESET_NAME = "Agent Control main protection"


def run(*args: str, input_text: str | None = None) -> str:
    p = subprocess.run(args, input=input_text, text=True, capture_output=True)
    if p.returncode:
        raise SystemExit(f"$ {' '.join(args)}\n{p.stderr or p.stdout}")
    return p.stdout


def desired(checks: list[dict]) -> dict:
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["merge"],
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 0,
                    "required_review_thread_resolution": True,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [
                        {"context": row["name"], "integration_id": row["app_id"]} for row in checks
                    ],
                    "strict_required_status_checks_policy": True,
                    "do_not_enforce_on_create": False,
                },
            },
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Create the reference product governance ruleset.")
    ap.add_argument("--policy", type=Path, default=Path("policy.json"))
    ap.add_argument("--apply", action="store_true",
                    help="Actually create the ruleset. Without this flag only print the reviewed payload.")
    a = ap.parse_args()
    policy = json.loads(a.policy.read_text())
    repo = policy["product_repo"]
    payload = desired(policy["required_checks"])

    if not a.apply:
        print(json.dumps({"repository": repo, "payload": payload}, indent=2))
        return 0

    raw = run("gh", "api", f"repos/{repo}/rulesets", "--paginate", "--slurp")
    pages = json.loads(raw)
    existing = [row for page in pages for row in page] if pages and isinstance(pages[0], list) else pages
    matches = [r for r in existing if isinstance(r, dict) and r.get("name") == RULESET_NAME]
    if matches:
        raise SystemExit(
            f"{RULESET_NAME!r} already exists in {repo}. Refusing to replace or mutate governance; "
            "inspect it and validate that the active runtime adapter accepts the resulting governance."
        )
    created = json.loads(run(
        "gh", "api", f"repos/{repo}/rulesets", "-X", "POST", "--input", "-",
        input_text=json.dumps(payload),
    ))
    print(json.dumps({"created": created.get("id"), "repository": repo, "name": created.get("name")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
