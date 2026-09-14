# Portable JSON Schema contracts

Contract: `gitops-agent-control-plane/v5`.

Schemas use JSON Schema Draft 2020-12 syntax but the repository intentionally implements a documented subset. The validator rejects unsupported keywords instead of silently ignoring constraints.

Coverage includes goal, policy, generated verification definitions, conformance scenarios, plan, durable state, terminal evidence, policy decisions, computed review, candidate/merge/post-merge evidence, diagnostic test evidence, signed controller-probe evidence, risk/recovery evidence and individual events.

`$id` is intentionally omitted until a stable public schema-resolution namespace is selected before the first tagged public release.
