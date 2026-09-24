#!/usr/bin/env python3
"""Read-only audit of repository publication settings using existing GitHub CLI auth.

All network requests use GET. The tool has no administrative mutation, visibility,
release, credential-reading or policy-application operation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
METADATA_FIELDS = {"description", "homepage", "has_issues", "allow_merge_commit",
                   "allow_update_branch", "delete_branch_on_merge"}
TAG_RULE_NAME = "public-release-tag-integrity"


class GhApi:
    """GET-only scoped transport; never print raw HTTP errors or credentials."""
    def __init__(self, repository: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid repository identity")
        self.prefix = "repos/" + repository

    def get(self, path: str) -> dict:
        if (path != self.prefix and not path.startswith(self.prefix + "/")) or ".." in path or "://" in path:
            raise ValueError("Read exceeds the selected repository")
        argv = ["gh", "api", "--hostname", "github.com", "--include", "--method", "GET",
                "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28", path]
        try:
            result = subprocess.run(argv, text=True, capture_output=True, timeout=45)
        except (OSError, subprocess.SubprocessError):
            return {"status": 0, "data": None, "reason": "cli-or-transport-unavailable"}
        text = result.stdout.replace("\r\n", "\n")
        match = re.match(r"HTTP/\S+\s+(\d{3})[^\n]*\n(.*?)\n\n(.*)\Z", text, re.DOTALL)
        if not match:
            return {"status": 0, "data": None, "reason": "unreadable-http-response"}
        status = int(match.group(1))
        if not 200 <= status < 300:
            return {"status": status, "data": None, "reason": "http-error"}
        if result.returncode:
            return {"status": 0, "data": None, "reason": "cli-failed-after-response"}
        try:
            data = json.loads(match.group(3)) if match.group(3).strip() else None
        except ValueError:
            return {"status": 0, "data": None, "reason": "invalid-json-response"}
        return {"status": status, "data": data, "has_next": 'rel="next"' in match.group(2)}

    def pages(self, path: str) -> dict:
        rows = []
        for page in range(1, 101):
            response = self.get(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            if response["status"] != 200 or not isinstance(response["data"], list):
                return {"status": response["status"], "data": None, "reason": "incomplete-collection"}
            rows.extend(response["data"])
            if not response.get("has_next"):
                return {"status": 200, "data": rows}
        return {"status": 0, "data": None, "reason": "pagination-bound-exceeded"}


def load_config(path: Path = ROOT / ".github/repository-settings.json") -> dict:
    config = json.loads(path.read_text())
    if config.get("schema") != 1 or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", config.get("repository", "")):
        raise ValueError("Invalid repository settings identity")
    if type(config.get("repository_id")) is not int or config["repository_id"] <= 0:
        raise ValueError("Expected a stable numeric repository ID")
    if set(config.get("metadata", {})) - METADATA_FIELDS or config["metadata"].get("allow_merge_commit") is not True:
        raise ValueError("Unsupported metadata field or incompatible merge policy")
    if type(config.get("minimum_reviews")) is not int or not 0 <= config["minimum_reviews"] <= 6:
        raise ValueError("Invalid minimum review count")
    checks = config.get("required_checks", [])
    if not checks or any(not isinstance(row.get("context"), str) or not row["context"] or type(row.get("app_id")) is not int or row["app_id"] <= 0 for row in checks):
        raise ValueError("Every required check needs a name and trusted App ID")
    if len({row["context"] for row in checks}) != len(checks):
        raise ValueError("Duplicate required check context")
    if not isinstance(config.get("topics"), list) or any(not re.fullmatch(r"[a-z0-9-]{1,50}", topic) for topic in config["topics"]):
        raise ValueError("Invalid repository topics")
    if not isinstance(config.get("branch"), str) or not config["branch"] or ".." in config["branch"]:
        raise ValueError("Invalid target branch")
    return config


def enabled(value: dict, field: str) -> bool:
    state = value.get(field, {})
    return state.get("enabled") is True if isinstance(state, dict) else state is True


def protection_satisfies(value: dict, config: dict) -> bool:
    checks = value.get("required_status_checks") or {}
    reviews = value.get("required_pull_request_reviews")
    observed = {(row.get("context"), row.get("app_id")) for row in checks.get("checks", [])}
    wanted = {(row["context"], row["app_id"]) for row in config["required_checks"]}
    return (checks.get("strict") is True and wanted <= observed
            and isinstance(reviews, dict)
            and type(reviews.get("required_approving_review_count")) is int
            and reviews["required_approving_review_count"] >= config["minimum_reviews"]
            and reviews.get("dismiss_stale_reviews") is True
            and not any((reviews.get("bypass_pull_request_allowances") or {}).values())
            and enabled(value, "enforce_admins") and enabled(value, "required_conversation_resolution")
            and value.get("allow_force_pushes", {}).get("enabled") is False
            and value.get("allow_deletions", {}).get("enabled") is False
            and not enabled(value, "required_linear_history"))


def observe(api: GhApi, config: dict) -> dict:
    base = api.prefix
    branch = base + "/branches/" + quote(config["branch"], safe="")
    paths = {"repository": base, "branch": branch, "protection": branch + "/protection",
             "workflow_permissions": base + "/actions/permissions/workflow",
             "actions_permissions": base + "/actions/permissions",
             "fork_approval": base + "/actions/permissions/fork-pr-contributor-approval",
             "private_reporting": base + "/private-vulnerability-reporting",
             "dependabot_alerts": base + "/vulnerability-alerts", "topics": base + "/topics"}
    values = {key: api.get(path) for key, path in paths.items()}
    values["branch_rules"] = api.pages(base + "/rules/branches/" + quote(config["branch"], safe=""))
    rules = api.pages(base + "/rulesets?includes_parents=true")
    values["tag_rule"] = {"status": rules["status"], "data": None}
    if rules["status"] == 200 and isinstance(rules["data"], list):
        matching = [row for row in rules["data"] if row.get("name") == TAG_RULE_NAME]
        if len(matching) > 1:
            values["tag_rule"] = {"status": 0, "data": None, "reason": "ambiguous-ruleset-name"}
        elif matching:
            values["tag_rule"] = api.get(base + "/rulesets/" + str(matching[0]["id"]))
    return values


def tag_rule_valid(value: dict | None) -> bool:
    return (isinstance(value, dict) and value.get("target") == "tag" and value.get("enforcement") == "active"
            and not value.get("bypass_actors")
            and {"update", "deletion"} <= {row.get("type") for row in value.get("rules", [])}
            and "refs/tags/v*" in value.get("conditions", {}).get("ref_name", {}).get("include", [])
            and not value.get("conditions", {}).get("ref_name", {}).get("exclude"))


def audit(config: dict, observations: dict) -> dict:
    repo, branch = observations["repository"].get("data"), observations["branch"].get("data")
    if observations["repository"]["status"] != 200 or not isinstance(repo, dict) or repo.get("full_name") != config["repository"] or repo.get("id") != config["repository_id"]:
        raise ValueError("Repository identity is not verified")
    if observations["branch"]["status"] != 200 or not isinstance(branch, dict) or branch.get("name") != config["branch"] or not re.fullmatch(r"[0-9a-f]{40}", branch.get("commit", {}).get("sha", "")):
        raise ValueError("Target branch identity is not verified")
    if repo.get("default_branch") != config["branch"] or type(repo.get("private")) is not bool:
        raise ValueError("Unexpected default branch or visibility state")
    controls = []
    def record(key, state, reason):
        controls.append({"key": key, "state": state, "reason": reason})
    def check(key, predicate, reason):
        value = observations[key]
        if value["status"] != 200 or not isinstance(value["data"], dict):
            record(key, "unknown", "Read unavailable or malformed; do not infer a disabled setting")
        else:
            record(key, "pass" if predicate(value["data"]) else "fail", reason)
    metadata_ok = all(repo.get(k) == v for k, v in config["metadata"].items())
    record("metadata", "pass" if metadata_ok else "fail", "Compare repository metadata with the desired baseline")
    check("topics", lambda data: set(config["topics"]) <= set(data.get("names", [])), "Existing additional topics need not be removed")
    protection = observations["protection"]
    if protection["status"] == 404 and branch.get("protected") is False:
        record("protection", "fail", "The branch is explicitly unprotected")
    else:
        check("protection", lambda data: protection_satisfies(data, config), "Classic protection baseline; a ruleset-only setup needs manual equivalent verification")
    rules = observations["branch_rules"]
    if rules["status"] != 200 or not isinstance(rules["data"], list):
        record("branch_rules", "unknown", "Effective branch rules unavailable")
    else:
        conflict = any(row.get("type") == "required_linear_history" for row in rules["data"])
        record("branch_rules", "fail" if conflict else "pass", "Linear history conflicts with the runtime's two-parent merge requirement; other rules still require review")
    check("workflow_permissions", lambda data: data.get("default_workflow_permissions") == "read" and data.get("can_approve_pull_request_reviews") is False, "Read-only token and no workflow review approval")
    check("actions_permissions", lambda data: data.get("enabled") is True, "Actions enabled; separately review allowed actions and runners")
    check("fork_approval", lambda data: data.get("approval_policy") == "all_external_contributors", "Approve external-contributor workflows before execution")
    if repo["private"]:
        record("private_reporting", "deferred", "Enable and externally test the reporting route at the separately authorized public transition")
    else:
        check("private_reporting", lambda data: data.get("enabled") is True, "External submission and notification delivery remain manual launch gates")
    alerts = observations["dependabot_alerts"]
    record("dependabot_alerts", "pass" if alerts["status"] == 204 else "unknown", "Only the successful 204 read proves alerts enabled")
    security = repo.get("security_and_analysis")
    if not isinstance(security, dict):
        record("secret_scanning", "unknown", "Security feature state is not exposed to this credential")
    else:
        secure = all(security.get(key, {}).get("status") == "enabled" for key in ("secret_scanning", "secret_scanning_push_protection"))
        record("secret_scanning", "pass" if secure else "fail", "Review feature availability without silently purchasing or enabling paid features")
    tags = observations["tag_rule"]
    if tags["status"] != 200:
        record("tag_rule", "unknown", "Tag rulesets are unavailable or ambiguous")
    else:
        record("tag_rule", "pass" if tag_rule_valid(tags["data"]) else "fail", "Verify a no-bypass v* tag update/deletion restriction")
    return {"schema": 1, "scope": "read-only-repository-settings", "repository": config["repository"],
            "main_sha": branch["commit"]["sha"], "private": repo["private"], "controls": controls,
            "observed_http_status": {k: v["status"] for k, v in observations.items()},
            "settings_passed": all(row["state"] == "pass" for row in controls),
            "public_visibility_authorized": False, "settings_changed": False,
            "manual_controls": ["administrator 2FA and recovery", "application permissions",
                                "inherited rules, Actions allowlist and runner policy", "external reporting and notifications",
                                "history and non-Git disclosure review", "provenance and trademark rights"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit",))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        config = load_config()
        if args.output:
            destination = args.output.resolve()
            if destination == ROOT or ROOT in destination.parents:
                raise ValueError("Write administrator evidence outside the source checkout")
        api = GhApi(config["repository"])
        report = audit(config, observe(api, config))
        report["observed_at"] = datetime.now(timezone.utc).isoformat()
        text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        print(text, end="")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text)
        return 0 if report["settings_passed"] else 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"GitHub settings audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
