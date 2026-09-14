# Verification

The current portable contract is:

```text
gitops-agent-control-plane/v3
```

## `./scripts/agentctl validate`

Validation is intentionally executable and non-mutating with respect to the example source tree.

It performs:

1. publication/licensing checks;
2. JSON Schema loading plus static goal/policy validation;
3. authority-layout validation using the same path matcher as runtime gates;
4. Python and shell syntax checks;
5. example baseline verification in a temporary copy;
6. unit tests over matcher, risk, review, executor timeout, event-chain boundary and harness failure behavior;
7. the full conformance matrix.

## Supported Python range

GitHub Actions executes validation on:

- Python 3.11;
- Python 3.12;
- Python 3.13.

This specifically protects the reference from interpreter-dependent glob behavior. Policy matching is implemented by the reference rather than delegated to version-dependent `Path.glob("**")` behavior.

## Conformance scenarios

The matrix currently covers ten independent behaviors:

- successful low-risk lifecycle;
- forbidden authority path;
- protected baseline-test tampering;
- executable implementation failure;
- insufficient/tautological acceptance testing;
- pre-write budget rejection;
- goal risk-ceiling rejection;
- reachable MEDIUM risk plus independent auto-merge ceiling;
- top-level HIGH security path plus human gate;
- actual process termination and recovery of an already-performed merge effect.

The harness catches per-scenario failures, continues remaining scenarios and persists a structured `conformance-report.json`.

## Schema validation

Emitted safety artifacts are validated against repository JSON Schemas, including policy decisions, review, test evidence, candidate/merge evidence, recovery, risk, durable state, terminal evidence and individual events.

## What verification does not prove

It does not prove that:

- the local executor is safe for untrusted/model-generated code;
- the unkeyed event chain is authentic against a full evidence-directory rewriter;
- a remote Git provider or external CI integration is configured safely;
- deterministic fixture roles have the capabilities of a production reasoning model.

Those boundaries are deliberate and documented rather than silently promoted to guarantees.
