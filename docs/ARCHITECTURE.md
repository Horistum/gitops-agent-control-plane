# Architecture

## Purpose

The reference demonstrates a control plane for autonomous engineering where a reasoning component can propose changes but cannot redefine product-authored authority.

The standalone reference **cannot guarantee adversarial evidence integrity for arbitrary candidate code** because candidate code still executes on the same host. Contract v4 therefore narrows the claim: the controller owns the verification protocol, exact Git binding and durable evidence, while production-grade hostile-code assurance still requires an isolated verifier/sandbox boundary.

## Four independent concerns

### Product authority

The product owns roadmap, structured forbidden paths, verification probes and quality gates.

Authority describes **what is allowed and what success means**. Human-readable `authority.md` and `architecture.md` are context; structured JSON files are the executable authority inputs.

### Reasoning roles

Discovery, architecture, developer, tester and reviewer produce structured artifacts.

Reasoning may propose and assess. A reasoning artifact is never accepted as proof that a command, probe, merge or state write happened.

### Controller/executor

The controller owns path checks, state transitions, Git mutations, risk evaluation, process execution and evidence persistence.

JUnit produced inside the candidate process is diagnostic only. Authoritative verification in the standalone reference comes from **product-authored controller probes** executed one probe per fresh process with controller completion receipts, negative controls and exact-SHA binding.

This is still not equivalent to a hostile-code sandbox. Candidate code executed by a probe can affect its own process, so production adapters must move the verifier across a stronger isolation boundary.

### Evidence

Evidence binds controller-observed claims to identities such as authority digests, protected probe IDs, candidate SHA, merge SHA, event-chain hash and pending-effect request hash.

The trust levels are deliberately different:

- role statements: explanation only;
- candidate-process JUnit: diagnostic evidence only;
- controller probe receipts: authoritative **within the trusted-fixture standalone scope**;
- production hostile-code evidence: requires an external/isolation boundary not provided here.

## Verification protocol

For a new roadmap behavior the controller:

1. verifies protected baseline probes against the baseline Git SHA;
2. runs the new acceptance probes against the baseline and requires them to fail (negative control);
3. creates the candidate;
4. runs each required product-authored probe in a fresh process against the exact candidate SHA;
5. requires a controller-recognized completion receipt for every probe;
6. treats JUnit as supplemental diagnostics only;
7. repeats controller probes after merge against the exact merge SHA.

A child process that merely exits `0` without a completion receipt does not pass a probe.

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
  -> baseline negative control
  -> candidate Git commit
  -> controller probes + diagnostic tests
  -> computed review
  -> risk/human-authority decision
  -> merge
  -> post-merge controller probes
  -> completion evidence
```

Negative outcomes are first-class terminal states, not exceptions to be hidden.

## Single source of truth

Product intent lives in `.agent-control/`.
Run state lives in `state.json`.
Event history lives in `events.jsonl`.

Human-readable summaries are projections of those facts, not competing databases.

## External-effect rule

Before an effect that cannot safely be repeated, persist:

1. effect kind;
2. exact request identity;
3. relevant candidate/base identity.

After the effect, persist the result and consume the pending intent.

The crash-recovery showcase demonstrates this with merge intent and an exact final `Effect-Id` Git trailer.
