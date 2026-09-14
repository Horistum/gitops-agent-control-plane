# Portable JSON Schema contracts

Contract: `gitops-agent-control-plane/v6`.

Schemas use Draft 2020-12 syntax through an intentionally explicit supported subset. Unsupported keywords fail validation rather than being silently ignored. The subset supports boolean or schema-valued `additionalProperties`, allowing digest maps and similar evidence structures to be typed.

Coverage includes goal, policy, generic verification definitions, conformance scenarios, request/proposal/plan, durable state, authority snapshots, protected-test snapshots, diagnostic tests, signed per-case probe evidence, policy/review/risk decisions, merge intent, merge/post-merge/recovery evidence, human-decision evidence, role/fault-injection artifacts, terminal evidence and events.

Semantic probe-DSL validation supplements JSON Schema for generator/expression-specific constraints.

`$id` is intentionally omitted until a stable public schema-resolution namespace is selected before the first tagged public release.
