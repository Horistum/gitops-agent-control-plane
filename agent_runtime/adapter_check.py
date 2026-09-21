#!/usr/bin/env python3
"""Self-certify a reasoning.kind=command adapter against the published contract.

See docs/ADAPTERS.md. The default run is free: it validates the policy's
reasoning block and drives only the zero-cost readiness handshake. --live adds
one real dispatched call per selected phase through the exact Reasoning
transport the controller uses, so it can spend real quota/credit; it is never
run without that explicit flag.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

from agent_runtime.contracts import POLICY_SCHEMA, ROLE_SCHEMAS
from agent_runtime.io import Closed, Unavailable, NotDispatched, read_json
from control_plane_core import fingerprint
from agent_runtime.reasoning import Reasoning
from control_plane_core.schema import SchemaValidationError, validate_instance

ALL_PHASES = tuple(ROLE_SCHEMAS)


def synthetic_payload(phase, effect_id):
    payload = {"phase": phase, "goal": {"objective": "Self-certification request; produce a schema-valid response.",
        "items": []}, "task": {"id": "SELF-CERT-001", "phase": phase}, "sources": {}, "omitted_paths": [],
        "memory": {}, "authority": {"allowed_paths": [], "test_paths": [], "protected_paths": []},
        "criteria": [], "self_certification": True, "effect_id": effect_id}
    if phase == "discovery":
        payload["eligible_items"] = ["SELF-CERT-001"]
    return payload


def verify(policy, *, live, phases):
    if not isinstance(policy, dict) or not isinstance(policy.get("reasoning"), dict):
        return {"passed": False, "stage": "policy_schema", "reason": "Missing reasoning configuration"}
    reasoning_config = policy["reasoning"]
    try:
        validate_instance(reasoning_config, POLICY_SCHEMA["properties"]["reasoning"])
    except SchemaValidationError as exc:
        return {"passed": False, "stage": "policy_schema", "reason": str(exc)}
    if reasoning_config["kind"] != "command":
        return {"passed": False, "stage": "policy_schema",
                "reason": "This script certifies reasoning.kind=command adapters; " + reasoning_config["kind"] + " uses a different transport"}
    if reasoning_config.get("protocol", 1) == 2 and not reasoning_config.get("model", "").strip():
        return {"passed": False, "stage": "policy_schema", "reason": "Protocol 2 requires an explicit model"}
    result = {"passed": True, "protocol": reasoning_config.get("protocol", 1), "stage": "readiness", "phases": {}}
    adapter = Reasoning(reasoning_config)
    try:
        result["readiness"] = adapter.preflight(readiness=True)
    except (Closed, Unavailable, OSError, ValueError) as exc:
        result.update(passed=False, reason=str(exc))
        return result
    if any(value != "passed" for value in result["readiness"]["checks"].values()):
        result.update(passed=False, reason="Readiness incomplete; configure an explicit check_argv handshake")
        return result
    if not live:
        result["stage"] = "readiness_only"
        return result
    result["stage"] = "live"
    result["certification_id"] = uuid.uuid4().hex
    phases = list(dict.fromkeys(phases))
    if not phases or any(phase not in ALL_PHASES for phase in phases):
        return {"passed": False, "stage": "phase_selection", "reason": "Select supported phases"}
    for index, phase in enumerate(phases):
        identity = fingerprint({"certification": result["certification_id"], "phase": phase, "index": index})
        row = {"effect_id": identity, "passed": False, "dispatch_attempted": False}
        result["phases"][phase] = row
        try:
            adapter.prepare()
            row["dispatch_attempted"] = True
            outcome = adapter.execute(synthetic_payload(phase, identity))
            row.update(protocol_error=outcome.get("protocol_error"), usage=outcome.get("usage", {}),
                       provider=outcome.get("provider", {}))
            row["passed"] = not outcome.get("protocol_error") and "result" in outcome
            if row["passed"]:
                row["result_keys"] = sorted(outcome["result"])
        except (Closed, Unavailable, OSError, ValueError) as exc:
            row.update(reason="Adapter failed; raw response and credentials withheld", outcome="unknown")
            if not row["dispatch_attempted"] or isinstance(exc, NotDispatched):
                row.update(dispatch_attempted=False, outcome="not_dispatched")
        finally:
            adapter.discard_preparation()
        if not row["passed"]:
            result["passed"] = False
            result["not_attempted"] = phases[index + 1:]
            break  # No retries or extra paid probes after the first failed phase.
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True, help="Full operational policy.json")
    parser.add_argument("--live", action="store_true",
                        help="Spend one real dispatched call per selected phase; omit to run only the free readiness handshake")
    parser.add_argument("--phase", action="append", choices=[*ALL_PHASES, "all"],
                        help="Repeatable; defaults to 'discovery' alone when --live is set")
    args = parser.parse_args(argv)
    try:
        policy = read_json(args.policy)
    except (Closed, OSError, ValueError):
        print(json.dumps({"passed": False, "stage": "policy_read", "reason": "Cannot read a valid policy"}))
        return 1
    phases = list(dict.fromkeys(args.phase or ["discovery"]))
    if "all" in phases:
        phases = list(ALL_PHASES)
    if args.live:
        print(f"--live will dispatch {len(phases)} real call(s) through the configured adapter; "
              "this can spend quota or credit.", file=sys.stderr)
    result = verify(policy, live=args.live, phases=phases)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
