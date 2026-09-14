# Architecture

## Purpose

The reference demonstrates a control plane for autonomous engineering where a reasoning component can propose changes but cannot redefine product-authored authority.

The standalone reference **cannot guarantee adversarial evidence integrity for arbitrary candidate code** because candidate code still executes on the same host. Contract v5 narrows and strengthens the claim: the controller owns verifier definitions, fresh case generation, exact Git binding, the signed receipt protocol and durable evidence, while production-grade hostile-code assurance still requires an isolated verifier boundary.

## Four independent concerns

### Product authority

The product owns roadmap, structured forbidden paths, verification definitions and quality gates.

Authority describes **what is allowed and what success means**. Human-readable `authority.md` and `architecture.md` are context; structured JSON files are executable authority inputs.

The verification definition is versioned with product authority but is not copied into the candidate workspace. Runtime authority evidence binds its controller-side digest separately.

### Reasoning roles

Discovery, architecture, developer, tester and reviewer produce structured artifacts.

Reasoning may propose and assess. A reasoning artifact is never accepted as proof that a command, probe, merge or state write happened.

### Controller / verifier parent / candidate child

The controller owns path checks, state transitions, Git mutations, risk evaluation and evidence persistence.

For behavioral verification it starts a trusted verifier parent. The controller transfers a per-probe HMAC key, challenge and probe definition through an inherited anonymous control FD. These secrets are absent from argv and environment.

The verifier parent reads and closes that FD **before candidate code exists**. The parent never imports the candidate. It generates fresh cases from the probe definition, then launches a candidate child for each case. Each child receives only its current input and reports a raw return/exception outcome. The verifier parent owns the oracle comparison and final signed receipt.

Candidate-process JUnit remains diagnostic only.

### Evidence

Evidence binds controller-observed claims to identities such as authority digests, verifier-definition digest, probe IDs, signed receipt challenge, candidate SHA, merge SHA, event-chain hash and pending-effect request hash.

Trust levels are deliberately different:

- role statements: explanation only;
- candidate-process JUnit: diagnostic evidence only;
- raw candidate-child outcomes: untrusted observations evaluated by the verifier parent;
- HMAC-authenticated verifier-parent receipts: authoritative **within the trusted-fixture standalone scope**;
- production hostile-code evidence: requires an external/isolation boundary not provided here.

## Property-style verification protocol

Probe definitions contain generators and invariants rather than public fixed tuples. For a new roadmap behavior the controller:

1. verifies protected baseline property probes;
2. runs new acceptance properties against baseline and requires failure as a negative control;
3. creates the candidate;
4. generates fresh candidate cases at runtime;
5. executes candidate children against those cases;
6. verifies exactly one HMAC-authenticated parent receipt per probe;
7. computes review from those results plus policy/authority checks;
8. repeats independently generated probes after merge against the exact merge SHA.

The `probe-aware` negative scenario demonstrates why this matters: an implementation that only knows the old published `Ada Lovelace` example still passes classic JUnit but fails fresh generated cases.

## Receipt secrecy

A receipt challenge is not useful if it is handed to the evaluated code. Contract v5 therefore does not put the HMAC key, challenge or probe JSON in worker argv. The secret control FD is closed before candidate children are launched. Candidate stdout is captured by the verifier parent and is never forwarded as the final receipt stream.

The controller accepts exactly one receipt line and verifies its HMAC, challenge and probe identity.

## Remaining isolation boundary

This architecture substantially strengthens the standalone protocol but it is not a security sandbox. Candidate code remains on the same host and may attempt OS/process-level attacks outside the protocol model.

A production integration for arbitrary model-generated code must move candidate execution behind a container/VM/remote verifier boundary and protect the result channel independently.

## Why the example roles are deterministic

The standalone implementation deliberately uses deterministic role outputs. This removes model variability while exposing the surrounding controller behavior.

A production implementation may replace role producers with AI. It must not move authority enforcement, Git mutation, verifier identity or durable effect handling into the model session.

## Lifecycle

```text
goal
  -> discovery
  -> plan
  -> proposal
  -> write-boundary decision
  -> generated baseline/negative-control probes
  -> candidate Git commit
  -> diagnostic tests + signed randomized probes
  -> computed review
  -> risk/human-authority decision
  -> merge
  -> independently generated post-merge probes
  -> completion evidence
```

Negative outcomes are first-class terminal states, not exceptions to be hidden.

## Single source of truth

Product intent is authored under `.agent-control/`. Controller-only verifier definitions are read from the product source rather than the candidate copy. Run state lives in `state.json`; event history lives in `events.jsonl`.

Human-readable summaries are projections of those facts, not competing databases.

## External-effect rule

Before an effect that cannot safely be repeated, persist effect kind, exact request identity and relevant candidate/base identity. After the effect, persist the result and consume the pending intent.

The crash-recovery showcase demonstrates this with merge intent and an exact final `Effect-Id` Git trailer.
