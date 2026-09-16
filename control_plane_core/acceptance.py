"""Typed acceptance obligations with controller-owned evaluation stages."""
from __future__ import annotations

import copy
from pathlib import PurePosixPath
from .decisions import CoreError, _ids

__all__ = [
    "acceptance_contract", "evaluate_obligations", "evidence_status_valid",
    "test_criteria",
]

STAGES = {"behavior": "candidate", "compatibility": "candidate",
          "documentation": "candidate", "ci": "integration", "delivery": "postmerge"}
TEST_KINDS = {"behavior", "compatibility"}


def acceptance_contract(criteria, declarations=()):
    ids = _ids([r["id"] for r in criteria], "acceptance ids", nonempty=True)
    if not declarations:
        # Existing specifications retain their original executable semantics.
        # Migration never guesses a weaker type from natural-language keywords.
        return [{**copy.deepcopy(row), "kind": "behavior", "stage": "candidate",
                 "paths": [], "targets": []} for row in criteria]
    if not isinstance(declarations, list) or len(declarations) != len(ids):
        raise CoreError("Typed acceptance must classify every criterion exactly once")
    declared_ids = [r.get("criterion_id") for r in declarations]
    if len(set(declared_ids)) != len(ids) or set(declared_ids) != set(ids):
        raise CoreError("Typed acceptance identities differ from the approved specification")
    rows = []
    by_id = {r["criterion_id"]: r for r in declarations}
    for criterion in criteria:
        row = by_id[criterion["id"]]
        if set(row) != {"criterion_id", "kind", "paths", "targets"} or row["kind"] not in STAGES:
            raise CoreError("Unsupported acceptance kind or fields")
        paths, targets = row["paths"], row["targets"]
        if not isinstance(paths, list) or len(paths) > 24 or not isinstance(targets, list):
            raise CoreError("Acceptance evidence selectors must be bounded lists")
        if len(paths) != len(set(paths)) or len(targets) != len(set(targets)):
            raise CoreError("Duplicate acceptance evidence selector")
        if row["kind"] == "documentation":
            if not paths or targets:
                raise CoreError("Documentation criteria require exact documentation paths")
            for path in paths:
                p = PurePosixPath(path)
                if (p.is_absolute() or str(p) != path or any(x in {"..", ".git"} for x in p.parts)
                        or p.suffix.lower() not in {".md", ".rst", ".txt", ".adoc"}
                        or any(c in path for c in "*?[\\\n\r\x00")):
                    raise CoreError("Documentation evidence requires regular exact text paths")
        elif row["kind"] == "ci":
            if paths or not targets or not set(targets) <= {"candidate", "integration"}:
                raise CoreError("CI criteria require explicit candidate/integration targets")
        elif paths or targets:
            raise CoreError("This acceptance kind does not take selectors")
        rows.append({**copy.deepcopy(criterion), "kind": row["kind"], "stage": STAGES[row["kind"]],
                     "paths": list(paths), "targets": list(targets)})
    return rows


def test_criteria(criteria):
    return [r for r in criteria if r.get("kind", "behavior") in TEST_KINDS]


def evidence_status_valid(criterion, row, stage="candidate"):
    due = {"candidate": 0, "integration": 1, "postmerge": 2}
    expected = criterion.get("stage", "candidate")
    if expected not in due or stage not in due:
        raise CoreError("Unknown acceptance evidence stage")
    return (bool(str(row.get("evidence", "")).strip()) and
            row.get("status") == ("covered" if due[expected] <= due[stage] else "deferred"))


def evaluate_obligations(criteria, observations, *, stage):
    """No future obligation can pass by being omitted or labelled not applicable."""
    order = {"candidate": 0, "integration": 1, "postmerge": 2}
    if stage not in order:
        raise CoreError("Unknown verification stage")
    rows = []
    for criterion in criteria:
        due = order[criterion.get("stage", "candidate")] <= order[stage]
        passed = observations.get(criterion["id"]) is True if due else None
        rows.append({"id": criterion["id"], "stage": criterion.get("stage", "candidate"),
                     "status": "passed" if passed else ("failed" if due else "deferred")})
    return {"stage": stage, "passed": all(r["status"] != "failed" for r in rows),
            "complete": all(r["status"] == "passed" for r in rows), "rows": rows}
