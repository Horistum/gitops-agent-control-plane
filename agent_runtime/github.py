"""Authenticated GitHub observations, idempotent PR publication and exact merge."""
from __future__ import annotations

import os
from urllib import error, parse, request
from control_plane_core import require_revision_identity, trusted_checks_pass
from .git import sha
from .io import Closed, Unavailable, canonical, loads


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Closed("GitHub redirects are forbidden")


class GitHub:
    def __init__(self, configuration, branch, transport=None):
        self.config, self.branch = configuration, branch
        self.prefix = "/repos/" + configuration["repository"]
        self.transport = transport
        self.opener = request.build_opener(NoRedirect())

    def api(self, path, method="GET", body=None, optional=False):
        if (path != self.prefix and not path.startswith(self.prefix + "/")) or ".." in path:
            raise Closed("GitHub path exceeds configured repository")
        if self.transport:
            return self.transport(path, method, body)
        token = os.environ.get(self.config["token_env"], "")
        if not token:
            raise Closed("Missing controller GitHub credential")
        req = request.Request("https://api.github.com" + path, method=method,
            data=canonical(body) if body is not None else None,
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
                     "User-Agent": "gitops-agent-control-plane"})
        try:
            with self.opener.open(req, timeout=45) as response:
                data = response.read(8_000_001)
                if len(data) > 8_000_000:
                    raise Closed("GitHub response exceeds byte limit")
                return loads(data) if data else None
        except error.HTTPError as exc:
            if optional and exc.code == 404:
                return None
            if exc.code in {408, 409, 429, 500, 502, 503, 504}:
                raise Unavailable(f"GitHub HTTP {exc.code}; writes require reconciliation") from None
            raise Closed(f"GitHub HTTP {exc.code}; authority/credential gate closed") from None
        except (error.URLError, TimeoutError):
            raise Unavailable("GitHub observation unavailable") from None

    def pages(self, path, key=None):
        rows = []
        for page in range(1, 51):
            value = self.api(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            part = value[key] if key else value
            if not isinstance(part, list):
                raise Closed("Malformed paginated GitHub response")
            rows.extend(part)
            if len(part) < 100:
                return rows
        raise Closed("Refusing incomplete GitHub pagination")

    def checks(self, revision):
        rows = self.pages(self.prefix + "/commits/" + sha(revision) + "/check-runs", "check_runs")
        if any(row.get("head_sha") != revision for row in rows):
            raise Closed("Check observation names another revision")
        observed = [{"id": row["id"], "name": row["name"], "app_id": row.get("app", {}).get("id"),
                     "status": row["status"], "conclusion": row["conclusion"]} for row in rows]
        latest = {}
        wanted = {(row["name"], row["app_id"]) for row in self.config["required_checks"]}
        for row in observed:
            key = (row["name"], row["app_id"])
            if key in wanted and row["id"] > latest.get(key, {}).get("id", -1):
                latest[key] = row
        failed = any(row["status"] == "completed" and row["conclusion"] != "success" for row in latest.values())
        return {"sha": revision, "passed": trusted_checks_pass(self.config["required_checks"], observed),
                "failed": failed, "checks": observed}

    def pull(self, number):
        if type(number) is not int or number < 1:
            raise Closed("Invalid pull request number")
        return self.api(self.prefix + f"/pulls/{number}")

    def identity(self, pull, base, head):
        if (pull.get("base", {}).get("ref") != self.branch
                or pull.get("base", {}).get("repo", {}).get("full_name") != self.config["repository"]
                or pull.get("head", {}).get("repo", {}).get("full_name") != self.config["repository"]):
            raise Closed("Pull request repository/base differs")
        require_revision_identity({"base": base, "head": head},
            {"base": pull.get("base", {}).get("sha"), "head": pull.get("head", {}).get("sha")})

    def publish(self, repo, branch, base, head, title):
        query = parse.urlencode({"state": "all", "head": self.config["repository"].split("/")[0] + ":" + branch,
                                 "base": self.branch})
        existing = self.pages(self.prefix + "/pulls?" + query)
        if len(existing) > 1:
            raise Closed("Ambiguous publication identity")
        if existing:
            pull = existing[0]
            previous = pull.get("head", {}).get("sha")
            if previous != head and pull.get("state") == "open" and not pull.get("merged_at"):
                # Repairs and base refreshes extend the published candidate; an
                # unrelated external rewrite must never be silently overwritten.
                self.identity(pull, base, previous)
                repo.text("merge-base", "--is-ancestor", sha(previous), sha(head))
                repo.publish_branch(branch, head)
                pull = self.pull(pull["number"])
            self.identity(pull, base, head)
            if pull["state"] != "open" and not pull.get("merged_at"):
                raise Closed("Published pull request was closed without merge")
        else:
            if repo.remote_base() != base:
                raise Closed("Remote base moved before publication")
            repo.publish_branch(branch, head)
            pull = self.api(self.prefix + "/pulls", "POST", {"head": branch, "base": self.branch,
                "title": title[:200], "body": "Controller-verified candidate. Exact source, test and review receipts remain in the owner-held run directory.",
                "draft": False})
            self.identity(pull, base, head)
        return {"number": pull["number"], "head": head, "base": base, "url": pull["html_url"]}

    def preflight(self):
        metadata = self.api(self.prefix)
        if metadata.get("allow_merge_commit") is not True:
            raise Closed("This runtime requires two-parent GitHub merge commits")
        self.governance()
        return {"repository": self.config["repository"], "merge_commits": True, "governance": "verified"}

    def governance(self):
        """Require strict server-side checks; never use an administrator bypass."""
        encoded = parse.quote(self.branch, safe="")
        protection = self.api(self.prefix + "/branches/" + encoded + "/protection", optional=True)
        required = {(row["name"], row["app_id"]) for row in self.config["required_checks"]}
        if protection:
            checks = protection.get("required_status_checks") or {}
            observed = {(row.get("context"), row.get("app_id")) for row in checks.get("checks", [])}
            reviews = protection.get("required_pull_request_reviews") or {}
            bypass = reviews.get("bypass_pull_request_allowances") or {}
            if (not any(bypass.values()) and checks.get("strict") is True and required <= observed
                    and protection.get("required_pull_request_reviews") is not None
                    and protection.get("required_conversation_resolution", {}).get("enabled") is True
                    and protection.get("allow_force_pushes", {}).get("enabled") is False
                    and protection.get("allow_deletions", {}).get("enabled") is False
                    and protection.get("enforce_admins", {}).get("enabled") is True):
                return
        effective = self.pages(self.prefix + "/rules/branches/" + encoded)
        ids = {row.get("ruleset_id") for row in effective if row.get("ruleset_id")}
        types, checks_ok = set(), False
        for identity in ids:
            rule = self.api(self.prefix + f"/rulesets/{identity}")
            if rule.get("enforcement") != "active" or rule.get("bypass_actors"):
                continue
            for entry in rule.get("rules", []):
                types.add(entry["type"])
                if entry["type"] == "pull_request" and not entry.get("parameters", {}).get("required_review_thread_resolution"):
                    types.discard("pull_request")
                if entry["type"] == "required_status_checks":
                    params = entry.get("parameters", {})
                    observed = {(row.get("context"), row.get("integration_id")) for row in params.get("required_status_checks", [])}
                    checks_ok |= params.get("strict_required_status_checks_policy") is True and required <= observed
        if not checks_ok or not {"pull_request", "deletion", "non_fast_forward"} <= types:
            raise Closed("Required server-side PR, strict trusted checks and no-bypass governance absent")

    def merge(self, number, base, head):
        pull = self.pull(number)
        self.identity(pull, base, head)
        if pull.get("merged_at"):
            return sha(pull["merge_commit_sha"])
        self.governance()
        if pull.get("state") != "open" or pull.get("draft"):
            raise Closed("Pull request is not ready for merge")
        if pull.get("mergeable") is not True or pull.get("mergeable_state") != "clean":
            raise Unavailable("GitHub mergeability/review/strict checks are not ready")
        if not self.checks(head)["passed"]:
            raise Unavailable("Exact candidate checks are not successful")
        result = self.api(self.prefix + f"/pulls/{number}/merge", "PUT", {"sha": head, "merge_method": "merge"})
        if result.get("merged") is not True:
            raise Unavailable("Merge outcome not confirmed; reconcile pull request")
        return sha(result["sha"])
