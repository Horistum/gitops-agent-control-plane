from __future__ import annotations

from pathlib import Path
import re

from ._schema_validation_impl import *  # noqa: F401,F403
from . import _schema_validation_impl as _base


ARTIFACT_SCHEMAS = dict(_base.ARTIFACT_SCHEMAS)
ARTIFACT_SCHEMAS.update({
    "control-state-intent.json": "control-state-intent.schema.json",
    "control-state-recovery.json": "control-state-recovery.schema.json",
    "phase-recovery.json": "phase-recovery.schema.json",
})

ARTIFACT_SCHEMA_PATTERNS = _base.ARTIFACT_SCHEMA_PATTERNS + (
    (
        re.compile(r"^control-state-intent-example-\d{3}\.json$"),
        "control-state-intent.schema.json",
    ),
    (
        re.compile(r"^retry-preconditions-example-\d{3}-attempt-\d{2}\.json$"),
        "retry-preconditions.schema.json",
    ),
)


def validate_evidence_directory(repository_root: Path, evidence: Path) -> list[str]:
    validated: list[str] = []
    for filename, schema_name in ARTIFACT_SCHEMAS.items():
        path = evidence / filename
        if path.is_file():
            validate_json_file(path, repository_root / "schemas" / schema_name)
            validated.append(filename)
    for path in sorted(evidence.glob("*.json")):
        if path.name in ARTIFACT_SCHEMAS:
            continue
        for pattern, schema_name in ARTIFACT_SCHEMA_PATTERNS:
            if pattern.fullmatch(path.name):
                validate_json_file(path, repository_root / "schemas" / schema_name)
                validated.append(path.name)
                break
    events = evidence / "events.jsonl"
    if events.is_file():
        validate_jsonl_file(events, repository_root / "schemas" / "event.schema.json")
        validated.append("events.jsonl")
    return validated
