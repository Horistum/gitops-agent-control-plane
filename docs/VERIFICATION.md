# Verification

Current portable contract:

```text
gitops-agent-control-plane/v6
```

## Repository validation

`./scripts/agentctl validate` performs publication checks, fail-closed schema loading, static goal/policy/scenario/probe validation, authority-layout validation, Python/shell syntax checks, non-mutating baseline diagnostics, direct code-path unit tests and the full conformance matrix on the current interpreter.

GitHub Actions runs the same contract on Python 3.11, 3.12 and 3.13.

## Product-authored generic probe DSL

The product owns `examples/minimal-product/.agent-control/verification-probes.json`. The source definition is versioned authority but is omitted from the candidate workspace and bound into authority evidence by digest.

V6 probes are generic declarations rather than product-named control-plane functions. A probe declares:

- target source file and callable;
- a case count;
- zero or more positional-argument generators;
- zero or more named kwargs generators;
- either a `raises` oracle or `return-equals` with a declarative expression.

Generator primitives include constant/null/boolean/integer/choice/whitespace/text-token values. Expression primitives include literal, positional arg, kwarg, concat, whitespace split, join, lower/upper, strip and length. Product-specific semantics are composed in authority data instead of patched into the controller.

## Negative control is case-level

Acceptance probes run against the baseline before candidate work can use them as evidence. Contract v6 requires **every generated acceptance case** to complete and fail on the baseline. A probe where baseline already satisfies 9 of 10 cases no longer passes negative control merely because its aggregate result is false.

Regression probes have the opposite requirement: they must pass on baseline.

## Receipt protocol

For each probe the controller creates a fresh HMAC key and challenge and passes the control payload to a trusted verifier parent through an inherited pipe. The executor starts the reader before writing the payload, preventing pre-reader pipe-buffer deadlock.

The parent closes the control FD before launching candidate children. Candidate children receive only the current args/kwargs. Their stdout is captured as untrusted observation; it is never copied into the controller-facing receipt stream. The verifier parent evaluates the generic oracle and emits one HMAC-authenticated protocol-3 receipt. The controller requires exactly one final receipt and verifies HMAC, challenge and probe identity.

## Current-protocol attack coverage

`receipt-injection` writes a fake `REFERENCE_PROBE_RECEIPT=` line from candidate code using the **current** protocol path. Conformance only passes if evidence shows at least one such injection attempt actually executed and the controller still received exactly one valid parent-signed receipt per probe.

`probe-aware` implements the public diagnostic example plus a deliberately narrow ASCII subset. It is checked against the current `greet-unicode` product invariant, so the scenario no longer depends on a removed historical probe literal.

The existing empty-body, assertion-monkeypatch and JUnit-forgery attacks remain executable regression cases.

## Evidence schemas

Schema validation covers the core safety path, including requests, proposals, authority snapshots, protected-test snapshots, signed probe/per-case evidence, merge intent, merge/postmerge evidence, human decisions, recovery, roles and terminal summaries. The built-in Draft 2020-12 subset rejects unsupported keywords instead of ignoring them.

## What verification does not prove

It does not prove arbitrary hostile Python is contained, finite generated cases prove all possible behavior, or same-host process separation equals a VM/container/remote verifier. Candidate-child raw outcomes remain observations from a process executing candidate code.

Production hostile-code verification must cross a stronger isolation boundary whose verifier internals and result channel are outside candidate control.
