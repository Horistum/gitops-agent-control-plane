# Architecture

## Purpose

The reference demonstrates a control plane where reasoning may propose changes but cannot redefine product-authored authority.

The standalone reference **cannot guarantee adversarial evidence integrity for arbitrary candidate code** because candidate code still executes on the same host. Contract v6 therefore separates authority, generic verifier definition, candidate observation, verifier judgment and final evidence instead of collapsing them into one test process.

## Product authority

The product owns roadmap, structured forbidden paths, quality gates and verification definitions. The verifier definition is versioned with the product source, omitted from the candidate workspace, and bound by digest into authority evidence.

The product expresses behavioral checks through a small generic generator/expression DSL. The control plane is not allowed to grow product-specific oracle functions such as `greet-normalized`.

## Reasoning roles

Discovery, architect, developer, tester and reviewer produce structured artifacts. Their statements explain intent or assessment but never prove that a command, probe, merge or state transition happened.

## Controller / verifier parent / candidate child

The controller owns write/risk/budget decisions, Git effects, durable state and final evidence validation.

For behavioral verification it starts a trusted verifier parent with a private control payload delivered through an inherited FD. The verifier parent owns case generation and oracle evaluation and closes the private FD before candidate execution.

Each candidate child receives only the current args/kwargs and executes the declared target callable. Its stdout and raw return/exception record are untrusted observations captured by the parent. Candidate output never becomes the controller-facing final receipt stream.

The verifier parent emits one HMAC-authenticated receipt containing per-case results. The controller verifies its HMAC, challenge, probe identity and protocol.

## Case-level negative control

Regression probes must pass on baseline. New acceptance probes are also run on baseline, but **every generated acceptance case** must fail there. This prevents an aggregate false result from hiding that the baseline already satisfies most of a supposed new criterion.

## Current attack model

The `receipt-injection` fixture writes a fake final receipt line from candidate code. Evidence records that the injection attempt actually occurred while the parent channel remained singular and authenticated.

The `probe-aware` fixture deliberately overfits public diagnostics and a narrow ASCII domain. The current product-owned unicode property rejects it. This makes the scenario about the current oracle contract rather than an obsolete historical literal.

## Evidence trust levels

- role statements: explanation;
- candidate-process JUnit: diagnostic, not authoritative;
- candidate-child raw outcomes/stdout: untrusted observations;
- verifier-parent HMAC receipt: authoritative within the deterministic fixture scope;
- production hostile-code evidence: requires a stronger external isolation boundary.

Authority snapshots, protected-test snapshots, merge intent and human-decision evidence are schema-validated alongside the rest of the safety path.

## Lifecycle

```text
goal
  -> discovery
  -> plan
  -> proposal gates
  -> baseline regression probes
  -> every-case acceptance negative control
  -> candidate commit
  -> diagnostics + generic verifier probes
  -> computed review
  -> risk/human gate
  -> durable merge intent + merge
  -> fresh post-merge probes
  -> completion evidence
```

## Remaining isolation boundary

HMAC, private control FDs and generated invariants close specific protocol weaknesses. They are not a security sandbox. Production verification of arbitrary model-generated/malicious code must move candidate execution behind a container, VM or independently controlled remote verifier and protect the result channel outside candidate reach.
