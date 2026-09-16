from __future__ import annotations

import json
from pathlib import Path
import re


from control_plane_core.schema import SchemaValidationError, SUPPORTED_SCHEMA_KEYWORDS, validate_instance, validate_schema


def load_schema(path: Path) -> dict:
    value = json.loads(path.read_text())
    if value.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise SchemaValidationError(f"{path}: unexpected schema dialect")
    validate_schema(value, str(path))
    return value


def validate_json_file(instance_path: Path, schema_path: Path) -> None:
    validate_instance(json.loads(instance_path.read_text()), load_schema(schema_path))


def validate_jsonl_file(instance_path: Path, schema_path: Path) -> None:
    schema = load_schema(schema_path)
    for i, raw in enumerate(instance_path.read_text().splitlines(), 1):
        validate_instance(json.loads(raw), schema, f"$line[{i}]")


ARTIFACT_SCHEMAS = {
    "request.json": "request.schema.json",
    "goal.json": "goal.schema.json",
    "policy.json": "policy.schema.json",
    "contract-set.json": "contract-set.schema.json",
    "control-loop.json": "control-loop.schema.json",
    "goal-evaluation.json": "goal-evaluation.schema.json",
    "plan.json": "plan.schema.json",
    "proposal.json": "proposal.schema.json",
    "state.json": "state.schema.json",
    "run-summary.json": "evidence.schema.json",
    "policy-decision.json": "policy-decision.schema.json",
    "review.json": "review.schema.json",
    "candidate-evidence.json": "candidate-evidence.schema.json",
    "merge-intent.json": "merge-intent.schema.json",
    "merge-evidence.json": "merge-evidence.schema.json",
    "postmerge-evidence.json": "postmerge-evidence.schema.json",
    "recovery.json": "recovery.schema.json",
    "human-decision.json": "human-decision.schema.json",
    "fault-injection.json": "fault-injection.schema.json",
    "test-baseline.json": "test-evidence.schema.json",
    "test-candidate.json": "test-evidence.schema.json",
    "test-postmerge.json": "test-evidence.schema.json",
    "probe-baseline.json": "probe-evidence.schema.json",
    "probe-negative-control.json": "probe-evidence.schema.json",
    "probe-candidate.json": "probe-evidence.schema.json",
    "probe-postmerge.json": "probe-evidence.schema.json",
    "risk-decision.json": "risk-decision.schema.json",
}

ARTIFACT_SCHEMA_PATTERNS = (
    (re.compile(r"^authority-snapshot-(?:baseline|candidate)\.json$"), "authority-snapshot.schema.json"),
    (re.compile(r"^protected-tests-(?:baseline|candidate)\.json$"), "protected-tests.schema.json"),
    (re.compile(r"^role-[a-z0-9-]+\.json$"), "role.schema.json"),
    (re.compile(r"^feedback-example-\d{3}-attempt-\d{2}\.json$"), "feedback.schema.json"),
    (re.compile(r"^release-transition-example-\d{3}\.json$"), "release-transition.schema.json"),
    (re.compile(r"^human-decision-example-\d{3}-attempt-\d{2}\.json$"), "human-decision.schema.json"),
    (re.compile(r"^goal-evaluation-cycle-\d{2}\.json$"), "goal-evaluation.schema.json"),
    (re.compile(r"^probe-negative-control-example-\d{3}-cycle-\d{2}\.json$"), "probe-evidence.schema.json"),
    (re.compile(r"^test-baseline-example-\d{3}-cycle-\d{2}\.json$"), "test-evidence.schema.json"),
    (re.compile(r"^probe-baseline-example-\d{3}-cycle-\d{2}\.json$"), "probe-evidence.schema.json"),
    (re.compile(r"^test-candidate-example-\d{3}-attempt-\d{2}\.json$"), "test-evidence.schema.json"),
    (re.compile(r"^probe-candidate-example-\d{3}-attempt-\d{2}\.json$"), "probe-evidence.schema.json"),
    (re.compile(r"^candidate-evidence-example-\d{3}-attempt-\d{2}\.json$"), "candidate-evidence.schema.json"),
    (re.compile(r"^review-example-\d{3}-attempt-\d{2}\.json$"), "review.schema.json"),
    (re.compile(r"^risk-decision-example-\d{3}-attempt-\d{2}\.json$"), "risk-decision.schema.json"),
    (re.compile(r"^policy-decision-example-\d{3}-attempt-\d{2}\.json$"), "policy-decision.schema.json"),
    (re.compile(r"^proposal-example-\d{3}-attempt-\d{2}\.json$"), "proposal.schema.json"),
    (re.compile(r"^plan-example-\d{3}-attempt-\d{2}\.json$"), "plan.schema.json"),
    (re.compile(r"^merge-intent-example-\d{3}\.json$"), "merge-intent.schema.json"),
    (re.compile(r"^merge-evidence-example-\d{3}\.json$"), "merge-evidence.schema.json"),
    (re.compile(r"^test-postmerge-example-\d{3}\.json$"), "test-evidence.schema.json"),
    (re.compile(r"^probe-postmerge-example-\d{3}\.json$"), "probe-evidence.schema.json"),
    (re.compile(r"^postmerge-evidence-example-\d{3}\.json$"), "postmerge-evidence.schema.json"),
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

