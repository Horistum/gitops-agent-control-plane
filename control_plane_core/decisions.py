"""Deterministic authority decisions shared by fixture and live controllers.

Adapters authenticate and persist observations. These functions only decide from
explicit normalized input; they never read prose, execute code, or perform Git I/O.
"""
from __future__ import annotations

from collections import deque
import fnmatch
import re


class CoreError(ValueError):
    """Malformed authority or an observation that cannot authorize a transition."""


RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
MAX_ITEMS = 256


def risk_rank(value: str) -> int:
    if not isinstance(value, str) or value not in RISK_ORDER:
        raise CoreError("Unknown risk level")
    return RISK_ORDER[value]


def _ids(values, label: str, *, nonempty: bool = False, bounded: bool = True) -> list[str]:
    if not isinstance(values, (list, tuple)) or (bounded and len(values) > MAX_ITEMS):
        raise CoreError(f"{label} must be a bounded list")
    if nonempty and not values:
        raise CoreError(f"{label} must not be empty")
    if any(not isinstance(x, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", x)
           for x in values):
        raise CoreError(f"{label} contains an invalid item identity")
    if len({x.lower() for x in values}) != len(values):
        raise CoreError(f"{label} contains duplicate item identities")
    return list(values)


def goal_projection(requested, completed, items=None) -> dict:
    """Project requested work from controller-verified completion and intent.

items is an adapter-normalized list of {id, dependencies, ready}. Omitting it
computes completion only and grants no selection authority. Dependencies outside
the requested goal never expand its scope. They require independently verified
completion supplied by the adapter.
"""
    requested = _ids(requested, "requested", nonempty=True)
    # The active dependency graph is bounded; the lifetime completion ledger is not.
    completed = _ids(completed, "completed", bounded=False)
    done = set(completed)
    remaining = [x for x in requested if x not in done]
    eligible, blocked, unavailable = [], {}, []
    if items is not None:
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise CoreError("Intent graph exceeds bounded item count")
        if any(not isinstance(x, dict) for x in items):
            raise CoreError("Intent graph rows must be objects")
        ids = _ids([x.get("id") for x in items], "intent graph")
        by_id = dict(zip(ids, items))
        if set(requested) - set(ids):
            raise CoreError("Requested item is absent from intent authority")
        indegree, children = {}, {x: [] for x in ids}
        for name, row in by_id.items():
            deps = _ids(row.get("dependencies"), f"dependencies of {name}")
            if type(row.get("ready")) is not bool:
                raise CoreError(f"Missing explicit readiness for {name}")
            if set(deps) - set(ids) - done:
                raise CoreError(f"Unknown dependency in intent authority: {name}")
            indegree[name] = len([x for x in deps if x in by_id])
            for dep in deps:
                if dep in children:
                    children[dep].append(name)
        queue = deque(x for x in ids if indegree[x] == 0)
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for child in children[current]:
                indegree[child] -= 1
                if not indegree[child]:
                    queue.append(child)
        if visited != len(ids):
            raise CoreError("Intent authority contains a dependency cycle")
        for name in remaining:
            row = by_id[name]
            missing = sorted(set(row["dependencies"]) - done)
            if missing:
                blocked[name] = missing
            if not row["ready"]:
                unavailable.append(name)
        # Stable authored order; a reasoning role may only choose within this set.
        eligible = [name for name in ids if name in remaining
                    and name not in blocked and by_id[name]["ready"]]
    return {"requested_items": requested,
            "completed_items": [x for x in requested if x in done],
            "remaining_items": remaining, "eligible_items": eligible,
            "blocked_dependencies": blocked, "unavailable_items": unavailable,
            "satisfied": not remaining,
            "success_condition_semantics": "reasoning_context"}


def merge_authority(risk: str, *, risk_ceiling: str, auto_merge_ceiling: str,
                    auto_merge_enabled: bool = True, human_gate_at: str = "high",
                    critical: bool = False) -> dict:
    """Human approval cannot widen the owner-authored hard risk ceiling."""
    rank, ceiling = risk_rank(risk), risk_rank(risk_ceiling)
    threshold = risk_rank(human_gate_at)
    if auto_merge_ceiling != "none":
        auto_rank = risk_rank(auto_merge_ceiling)
    else:
        auto_rank = -1
    if type(auto_merge_enabled) is not bool or type(critical) is not bool:
        raise CoreError("Merge controls must be explicit booleans")
    blocked = rank > ceiling
    human = rank >= threshold or critical
    auto = auto_merge_enabled and rank <= auto_rank
    reasons = []
    if blocked:
        reasons.append("RISK_CEILING")
    if human:
        reasons.append("HUMAN_GATE_THRESHOLD")
    if not auto:
        reasons.append("AUTO_MERGE_CEILING")
    return {"blocked": blocked, "human_gate_required": human,
            "auto_merge_allowed": not blocked and auto and not human,
            "requires_approval": not blocked and (human or not auto),
            "decision_reasons": reasons}


def path_allowed(path: str, allowed, protected=(), forbidden=()) -> bool:
    if (not isinstance(path, str) or not path or path.startswith("/")
            or "\\" in path or any(ord(x) < 32 or ord(x) == 127 for x in path)
            or any(x in ("", ".", "..", ".git") for x in path.split("/"))):
        return False
    for patterns in (allowed, protected, forbidden):
        if not isinstance(patterns, (list, tuple)) or any(not isinstance(x, str) or not x for x in patterns):
            raise CoreError("Path authority must contain explicit patterns")
    match = lambda patterns: any(fnmatch.fnmatchcase(path, p) for p in patterns)
    return match(allowed) and not match(protected) and not match(forbidden)


def _sha(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise CoreError("Missing or malformed exact Git revision")
    return value


def require_revision_identity(expected: dict, observed: dict) -> None:
    if not isinstance(expected, dict) or not expected or not isinstance(observed, dict):
        raise CoreError("Exact revision identity must be explicit")
    for key, value in expected.items():
        if _sha(value) != _sha(observed.get(key)):
            raise CoreError(f"Exact revision identity mismatch: {key}")


def require_merge_identity(base: str, candidate: str, parents) -> None:
    if not isinstance(parents, (list, tuple)) or len(parents) != 2:
        raise CoreError("A verified merge must have exactly two parents")
    require_revision_identity({"base": base, "candidate": candidate},
                              {"base": parents[0], "candidate": parents[1]})


def trusted_checks_pass(required, observed) -> bool:
    """Require latest successful named checks from the declared trusted provider."""
    if not isinstance(required, list) or not required or not isinstance(observed, list):
        return False
    wanted = []
    for row in required:
        if (not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]
                or type(row.get("app_id")) is not int or row["app_id"] <= 0):
            return False
        wanted.append((row["name"], row["app_id"]))
    if len(set(wanted)) != len(wanted):
        return False
    latest = {}
    for row in observed:
        if not isinstance(row, dict):
            return False
        name, app = row.get("name"), row.get("app_id")
        if not isinstance(name, str) or type(app) is not int:
            return False
        key = (name, app)
        if key not in wanted:
            continue
        identity = row.get("id", 0)
        if type(identity) is not int or identity < 0:
            return False
        previous = latest.get(key)
        if previous is not None and identity == previous.get("id", 0) and row != previous:
            return False
        if previous is None or identity > previous.get("id", 0):
            latest[key] = row
    return all(key in latest and latest[key].get("status") == "completed"
               and latest[key].get("conclusion") == "success" for key in wanted)


def completion_transition(requested, completed, item: str, *, merge_sha: str,
                          verification_passed: bool) -> dict:
    projection = goal_projection(requested, completed)
    if item not in projection["requested_items"]:
        raise CoreError("Cannot record completion outside goal authority")
    _sha(merge_sha)
    if verification_passed is not True:
        raise CoreError("Completion requires independently verified post-merge evidence")
    done = list(completed)
    if item not in done:
        done.append(item)
    return {"completed": done, "goal": goal_projection(requested, done)}
