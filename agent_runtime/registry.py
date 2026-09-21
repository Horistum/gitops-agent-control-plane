"""Read-only status over several local runs; no database, no new writer.

An owner running more than one goal has several independent run directories,
each already a valid RunService root. This module only aggregates their
existing status() projections; it never writes, never takes a writer lock,
and is not a second source of truth. See docs/HOSTING.md for why the runtime
stays single-host and file-backed rather than gaining a shared store here.
"""
from __future__ import annotations

from pathlib import Path

from .io import Closed
from .service import RunService

MAX_RUNS = 512


def discover_runs(root, *, limit=MAX_RUNS):
    """Runs under one flat registry root: root itself, or its immediate children.

    Non-recursive and bounded on purpose: a registry root is an owner-curated
    flat directory of runs (for example one parent directory a supervisor
    also iterates), not an arbitrary filesystem walk that could wander into
    an unrelated, large or symlinked tree.
    """
    root = Path(root).resolve()
    if type(limit) is not int or not 0 <= limit <= MAX_RUNS:
        raise Closed("Registry limit must be an integer between 0 and 512")
    def known_run(path):
        return (path / "state.json").exists() or (path / "initialization.json").is_file()
    if known_run(root):
        if limit == 0:
            raise Closed("Registry root exceeds the bounded run count")
        return [root]
    if not root.is_dir():
        raise Closed("Registry root is not an existing run or directory of runs")
    found = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        if known_run(child):
            if len(found) >= limit:
                raise Closed("Registry root exceeds the bounded run count")
            found.append(child)
    return found


def registry_status(root, *, limit=MAX_RUNS):
    """One best-effort snapshot per discovered run; one bad run cannot hide the rest."""
    runs = []
    for path in discover_runs(root, limit=limit):
        try:
            runs.append({"root": str(path), "readable": True, **RunService(path).status()})
        except (Closed, OSError, KeyError, TypeError, ValueError) as exc:
            runs.append({"root": str(path), "readable": False, "reason": str(exc)})
    return {"schema": 1, "root": str(Path(root).resolve()), "run_count": len(runs), "runs": runs}
