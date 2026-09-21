"""Receipt-derived operational accounting, deliberately not an invoice ledger."""
from __future__ import annotations

from .io import Closed

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens")


def validate_usage(value):
    if not isinstance(value, dict) or set(value) - set(TOKEN_FIELDS):
        raise Closed("Usage must contain only supported token counters")
    if any(type(v) is not int or not 0 <= v <= 10**12 for v in value.values()):
        raise Closed("Usage counters must be bounded nonnegative integers")
    if "cached_input_tokens" in value and ("input_tokens" not in value
            or value["cached_input_tokens"] > value["input_tokens"]):
        raise Closed("Cached tokens must be a subset of reported input tokens")
    return dict(value)


def usage_report(store):
    """Read only receipt identities reachable from one atomic state snapshot.

    A pending receipt may become durable while reading. It can replace that
    snapshot's unknown reservation, never add a later operation to the report.
    """
    state = store.state
    calls = []
    totals = {name: 0 for name in TOKEN_FIELDS}
    observations = {name: 0 for name in TOKEN_FIELDS}
    identities = set(state.get("receipts", {}))
    for intent in [*state.get("abandoned_effects", []), state.get("pending")]:
        if intent and (store.root / "receipts" / (intent["id"] + ".json")).exists():
            identities.add(intent["id"])
    for identity in sorted(identities):
        path = store.root / "receipts" / (identity + ".json")
        receipt = store.read_receipt(path.stem)
        request = receipt["request"]
        if request.get("kind") != "model":
            continue
        result = receipt["output"]
        if not isinstance(result, dict):
            raise Closed("Model receipt output must be an object")
        usage = validate_usage(result.get("usage", {}))
        for name, number in usage.items():
            totals[name] += number
            observations[name] += 1
        calls.append({"effect_id": path.stem, "item": request.get("item"),
            "attempt": request.get("attempt"), "phase": request["payload"].get("phase"),
            "status": "protocol_error" if result.get("protocol_error") else "recorded",
            "usage": usage, "provider": result.get("provider", {})})
    recorded = {row["effect_id"] for row in calls}
    uncertain = []
    for intent in [*state.get("abandoned_effects", []), state.get("pending")]:
        if intent and intent["kind"] == "model" and intent["id"] not in recorded:
            uncertain.append({"effect_id": intent["id"], "status": "unknown_outcome",
                              "abandoned": intent is not state.get("pending")})
    reserved = state["model_calls"]
    if len(calls) + len(uncertain) != reserved:
        raise Closed("Model reservations and durable receipt/intent accounting differ")
    return {"schema": 1, "run_id": state["run_id"], "revision": state.get("revision", 0), "reserved_calls": reserved,
        "recorded_calls": len(calls), "unknown_outcomes": len(uncertain),
        "protocol_errors": sum(row["status"] == "protocol_error" for row in calls),
        "reported_tokens": totals, "token_observations": observations,
        "calls_without_usage": sum(not row["usage"] for row in calls),
        "provider_reported": True, "billing_ready": False,
        "calls": calls, "uncertain_calls": uncertain}
