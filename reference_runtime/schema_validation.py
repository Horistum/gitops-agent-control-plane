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
    return _base.validate_evidence_directory(
        repository_root, evidence, artifact_schemas=ARTIFACT_SCHEMAS,
        artifact_schema_patterns=ARTIFACT_SCHEMA_PATTERNS,
    )
