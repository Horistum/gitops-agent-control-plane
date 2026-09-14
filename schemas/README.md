# Contract schemas

These JSON Schema documents describe the portable surfaces demonstrated by the reference runtime:

- `goal.schema.json` — owner intent and authority ceiling;
- `policy.schema.json` — write/risk/test boundaries;
- `plan.schema.json` — bounded architecture plan;
- `state.schema.json` — durable execution state;
- `evidence.schema.json` — terminal run evidence.

The standalone runtime performs dependency-free semantic validation so the demo needs only Python.
The schemas exist so other implementations can validate the same contracts with any standards-compliant JSON Schema tool.
