"""Complete merge receipts, bound to durable intent and observed Git identity."""
from __future__ import annotations

from control_plane_core import CoreError, require_merge_identity, validate_instance

from .base import PolicyConfigurationError
from .contracts import load_json, sha256_json
from .schema_validation import load_schema


class CandidateIdentityError(PolicyConfigurationError):
    """A merge or its persisted evidence does not match authorized revisions."""


_IDENTITY_FIELDS = {
    "base_sha", "actual_first_parent_sha", "actual_second_parent_sha",
    "candidate_identity_matches",
}
_REQUEST_FIELDS = ("effect", "candidate_sha", "base_sha", "candidate_branch")


def build_merge_receipt(engine, effect: dict, merge_sha: str, *, recovered_existing: bool) -> dict:
    parents = engine.git("show", "-s", "--format=%P", merge_sha, check=False).split()
    try:
        require_merge_identity(effect.get("base_sha"), effect.get("candidate_sha"), parents)
    except CoreError as exc:
        raise CandidateIdentityError(
            "merge commit parents do not match the exact reviewed base/candidate revisions"
        ) from exc
    intent = {"schema": 3, **effect}
    try:
        validate_instance(intent, load_schema(engine.repo / "schemas" / "merge-intent.schema.json"))
        request = {key: effect[key] for key in _REQUEST_FIELDS}
        if sha256_json(request) != effect["request_hash"]:
            raise ValueError("merge intent request hash mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateIdentityError(f"invalid durable merge intent: {exc}") from exc
    commits = engine._find_merge_effects(effect["request_hash"])
    if commits != [merge_sha]:
        raise CandidateIdentityError(
            f"merge effect identity mismatch: {commits} expected {[merge_sha]}"
        )
    receipt = {
        "schema": 2,
        "base_sha": effect["base_sha"],
        "candidate_sha": effect["candidate_sha"],
        "merge_sha": merge_sha,
        "request_hash": effect["request_hash"],
        "effect_occurrences": 1,
        "recovered_existing_effect": recovered_existing,
        "method": "runtime-profile-git-merge",
        "actual_first_parent_sha": parents[0],
        "actual_second_parent_sha": parents[1],
        "candidate_identity_matches": True,
    }
    validate_instance(receipt, load_schema(engine.repo / "schemas" / "merge-evidence.schema.json"))
    return receipt


def publish_merge_receipt(engine, receipt: dict) -> None:
    # Both complete projections must precede clearing the durable pending effect.
    engine.write_json("merge-evidence.json", receipt)
    engine.write_json(f"merge-evidence-{engine.state['current_item'].lower()}.json", receipt)


def ensure_merge_receipt(engine) -> None:
    """Validate before post-merge work; recover missing/legacy projections only.

    Existing contradictory or malformed evidence is never silently overwritten.
    Reconstruction requires the saved intent, current state and actual Git merge
    to agree. This is corruption detection, not authentication against an actor
    who can rewrite the entire run directory and repository.
    """
    item = engine.state.get("current_item")
    try:
        if not isinstance(item, str) or not item:
            raise ValueError("post-merge state lacks item identity")
        intent = load_json(engine.evidence / f"merge-intent-{item.lower()}.json")
        if not isinstance(intent, dict):
            raise ValueError("merge intent must be an object")
        generic_intent = engine.evidence / "merge-intent.json"
        if generic_intent.exists() and load_json(generic_intent) != intent:
            raise ValueError("merge intent projections disagree")
        effect = {key: value for key, value in intent.items() if key != "schema"}
        if intent.get("schema") != 3:
            raise ValueError("unsupported merge intent schema")
        for key, state_key in (("base_sha", "base_sha"), ("candidate_sha", "candidate_sha"),
                               ("candidate_branch", "current_candidate_branch")):
            if effect.get(key) != engine.state.get(state_key):
                raise ValueError(f"merge intent differs from saved state: {key}")
        names = ("merge-evidence.json", f"merge-evidence-{item.lower()}.json")
        existing = []
        for name in names:
            path = engine.evidence / name
            if not path.exists():
                existing.append(None)
                continue
            value = load_json(path)
            if not isinstance(value, dict):
                raise ValueError("merge receipt must be an object")
            existing.append(value)
        observed = next((value for value in existing if value is not None), None)
        recovered = observed.get("recovered_existing_effect") if isinstance(observed, dict) else True
        expected = build_merge_receipt(engine, effect, engine.state["merge_sha"],
                                       recovered_existing=recovered)
        for value in existing:
            if value is None:
                continue
            if not isinstance(value, dict) or set(expected) - set(value) - _IDENTITY_FIELDS:
                raise ValueError("merge receipt is not a supported legacy or complete receipt")
            if any(key not in expected or type(field) is not type(expected[key])
                   or field != expected[key] for key, field in value.items()):
                raise ValueError("merge receipt contradicts exact Git/intent identity")
        if any(value != expected for value in existing):
            publish_merge_receipt(engine, expected)
            engine.event("merge-receipt-reconciled", {
                "item": item, "merge_sha": expected["merge_sha"],
                "request_hash": expected["request_hash"],
            })
    except CandidateIdentityError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise CandidateIdentityError(f"merge receipt recovery blocked: {exc}") from exc
