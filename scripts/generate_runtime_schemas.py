#!/usr/bin/env python3
"""Generate operational schemas from the exact contracts consumed at runtime."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent_runtime.contracts import GOAL_SCHEMA, POLICY_SCHEMA, ROLE_SCHEMAS, PROVIDER_RESPONSE_SCHEMA


def projections():
    schemas = {"operational-policy": POLICY_SCHEMA, "operational-goal": GOAL_SCHEMA,
               "command-reasoning-response": PROVIDER_RESPONSE_SCHEMA,
               **{"role-" + phase: schema for phase, schema in ROLE_SCHEMAS.items()}}
    return {ROOT / "schemas" / (name + ".schema.json"): json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/Horistum/gitops-agent-control-plane/schemas/" + name + ".schema.json",
        **schema}, indent=2, ensure_ascii=False) + "\n" for name, schema in schemas.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, content in projections().items():
        if args.check:
            if not path.is_file() or path.read_text() != content:
                raise SystemExit("Generated runtime schema drift: " + path.name)
        else:
            path.write_text(content)
