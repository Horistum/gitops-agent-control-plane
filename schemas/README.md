# Portable JSON Schema contracts

Contract: `gitops-agent-control-plane/v3`.

Schemas use JSON Schema Draft 2020-12 and cover goal, policy, plan, durable state,
terminal evidence, policy decisions, computed review, candidate/merge/test/risk/recovery
evidence and individual events.

`$id` is intentionally omitted until a stable public schema-resolution namespace is
selected before the first tagged public release. Repository conformance validates emitted
artifacts against these schemas with the built-in supported-keyword validator.
