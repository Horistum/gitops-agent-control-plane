"""Explicit non-writing readiness checks; model access remains untested."""
from .contracts import validate_configuration
from .git import GitRepository
from .github import GitHub
from .io import Closed, Unavailable
from .reasoning import Reasoning
from .verification import Verification


def diagnose(policy, goal):
    validate_configuration(policy, goal)
    result = {"model_called": False, "checks": {}, "ready": False}
    probes = {"reasoning": lambda: Reasoning(policy["reasoning"]).preflight(readiness=True),
              "execution": lambda: Verification(policy["execution"]).preflight()}
    if policy["publication"]["kind"] == "github":
        probes["github_governance"] = lambda: GitHub(policy["publication"], policy["base_branch"]).preflight()
        def git_read():
            repo = GitRepository(policy["product"], policy["base_branch"])
            slug = policy["publication"]["repository"]
            if repo.text("remote", "get-url", "origin") not in {
                    f"https://github.com/{slug}", f"https://github.com/{slug}.git", f"git@github.com:{slug}.git"}:
                raise Closed("Git origin differs from authorized repository")
            repo.text("ls-remote", "--exit-code", "origin", "refs/heads/" + policy["base_branch"])
            return {"read": "passed", "write": "not_checked", "credentials": "git-transport"}
        probes["git_transport"] = git_read
    for name, probe in probes.items():
        try:
            result[name] = probe()
            subchecks = (result[name] or {}).get("checks", {})
            result["checks"][name] = "passed" if all(v == "passed" for v in subchecks.values()) else "not_checked"
        except (Closed, Unavailable, OSError, ValueError):
            result["checks"][name] = "failed"
            result[name] = {"reason": "Readiness failed; inspect this adapter's local configuration"}
    result["checks"]["live_model"] = "not_checked"
    result["ready"] = all(result["checks"][name] == "passed" for name in probes)
    return result
