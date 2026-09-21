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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_runtime.contracts import POLICY_SCHEMA, ROLE_SCHEMAS
from agent_runtime.io import Closed, Unavailable
from agent_runtime.reasoning import Reasoning
from control_plane_core.schema import SchemaValidationError, validate_instance

ALL_PHASES = tuple(ROLE_SCHEMAS)


def synthetic_payload(phase):
    payload = {"phase": phase, "goal": {"objective": "Self-certification request; produce a schema-valid response.",
        "items": []}, "task": {"id": "SELF-CERT-001", "phase": phase}, "sources": {}, "omitted_paths": [],
        "memory": {}, "authority": {"allowed_paths": [], "test_paths": [], "protected_paths": []},
        "criteria": [], "self_certification": True}
    if phase == "discovery":
        payload["eligible_items"] = ["SELF-CERT-001"]
    return payload


def verify(policy, *, live, phases):
    reasoning_config = policy["reasoning"]
    try:
        validate_instance(reasoning_config, POLICY_SCHEMA["properties"]["reasoning"])
    except SchemaValidationError as exc:
        return {"passed": False, "stage": "policy_schema", "reason": str(exc)}
    if reasoning_config["kind"] != "command":
        return {"passed": False, "stage": "policy_schema",
                "reason": "This script certifies reasoning.kind=command adapters; " + reasoning_config["kind"] + " uses a different transport"}
    result = {"passed": True, "protocol": reasoning_config.get("protocol", 1), "stage": "readiness", "phases": {}}
    adapter = Reasoning(reasoning_config)
    try:
        result["readiness"] = adapter.preflight(readiness=True)
    except (Closed, Unavailable) as exc:
        result.update(passed=False, reason=str(exc))
        return result
    if not live:
        result["stage"] = "readiness_only"
        return result
    result["stage"] = "live"
    for phase in phases:
        outcome = adapter.execute(synthetic_payload(phase))
        row = {"protocol_error": outcome.get("protocol_error"),
               "usage": outcome.get("usage", {}), "provider": outcome.get("provider", {})}
        if outcome.get("protocol_error"):
            row["passed"] = False
        else:
            row["result_keys"] = sorted(outcome.get("result", {}))
            row["passed"] = "result" in outcome
        result["phases"][phase] = row
        result["passed"] = result["passed"] and row["passed"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True, help="Full operational policy.json")
    parser.add_argument("--live", action="store_true",
                        help="Spend one real dispatched call per selected phase; omit to run only the free readiness handshake")
    parser.add_argument("--phase", action="append", choices=[*ALL_PHASES, "all"],
                        help="Repeatable; defaults to 'discovery' alone when --live is set")
    args = parser.parse_args(argv)
    policy = json.loads(args.policy.read_text())
    phases = args.phase or ["discovery"]
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
