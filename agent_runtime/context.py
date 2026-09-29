"""Bounded retrieval and independent role views, never execution authority."""
import copy
import re
from .io import Closed


def requested_context(engine, task, output):
    files = output.get("requested_files", [])
    searches = output.get("requested_searches", [])
    facts = output.get("requested_facts", [])
    if not (files or searches or facts):
        raise Closed("need_context requires files, literal searches or supported facts")
    found = engine.repo.search(task["head"], searches)
    observations = {}
    for fact in facts:
        if not engine.github or not re.fullmatch(r"pr:[1-9][0-9]{0,8}", fact):
            raise Closed("Supported facts are pr:N in the configured GitHub repository")
        pull = engine.github.pull(int(fact.split(":")[1]))
        observations[fact] = {key: pull.get(key) for key in ("number", "state", "merged_at", "merge_commit_sha")}
        observations[fact].update(head=pull.get("head", {}).get("sha"), base=pull.get("base", {}).get("sha"),
                                  repository=engine.policy["publication"]["repository"])
    task["search_results"] = found
    task["external_facts"] = observations
    task["requested_files"] = list(dict.fromkeys(files + [row["matches"][0]["excerpt"] for row in found.values() if row["matches"]]))


def role_view(task, phase):
    value = copy.deepcopy({key: item for key, item in task.items()
                           if key not in {"memory", "proposal", "frozen_tests", "role_results",
                                          "verification_recovery", "verification_recovery_history"}})
    if phase in {"reviewer", "challenge_review", "tester"}:
        value["feedback"] = [row for row in value.get("feedback", []) if row.get("phase") == phase]
    if phase == "challenge_review":
        for field in ("plan", "test_design"):
            value.pop(field, None)
    return value
