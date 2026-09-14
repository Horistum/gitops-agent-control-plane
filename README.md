# GitOps Agent Control Plane Reference

A **standalone executable reference** for policy-bounded autonomous software delivery through Git.

**Initiated and maintained by the Horistum project.**

This repository demonstrates control-plane mechanics, not a production AI product. It is deliberately small enough that every authority decision, Git identity, test result, review gate and recovery effect can be inspected.

The reference runs with **Bash, Git and Python 3.11+**. CI executes the same contract on Python 3.11, 3.12 and 3.13.

## One-command demo

```bash
./scripts/agentctl demo happy-path
```

A successful run creates a real local baseline commit, a separate candidate commit, executable verification bound to that candidate SHA, a computed review, a real non-fast-forward merge commit, post-merge verification bound to the merge SHA, durable state and evidence.

Evidence is written under `.demo/runs/<run-id>/evidence/`.

## Conformance is more important than the happy path

```bash
./scripts/agentctl conformance
```

Contract v3 currently exercises eleven scenarios discovered from `examples/scenarios/`:

| Scenario | Expected terminal state | Property |
|---|---|---|
| `happy-path` | `COMPLETED` | full bounded lifecycle |
| `forbidden-path` | `BLOCKED_POLICY` | authority rewrite rejected before candidate side effect |
| `test-tamper` | `BLOCKED_POLICY` | developer cannot replace protected baseline tests |
| `test-failure` | `FAILED_VERIFICATION` | executable failure blocks merge |
| `insufficient-tests` | `FAILED_VERIFICATION` | green-but-insufficient tests fail computed review |
| `budget-exceeded` | `BLOCKED_POLICY` | changed-file budget blocks before workspace mutation |
| `patch-budget-exceeded` | `BLOCKED_POLICY` | patch-byte budget is independently reachable at an allowed file count |
| `risk-ceiling` | `BLOCKED_POLICY` | effective risk may exceed owner goal authority |
| `medium-auto-boundary` | `NEEDS_DECISION` | MEDIUM is reachable and auto-merge ceiling is independent |
| `human-gate` | `NEEDS_DECISION` | top-level `src/security/**` is classified HIGH |
| `crash-recovery` | `COMPLETED` | a second process recovers an already-performed merge effect without duplicating it |

A conformance failure does not abort the matrix. Remaining scenarios continue and a structured `conformance-report.json` plus failure evidence are retained.

## Authority and tests are different write domains

Product-authored authority lives under:

```text
examples/minimal-product/.agent-control/
```

The standalone policy separates:

- developer write paths: implementation source only;
- tester write paths: new independent acceptance-test files only;
- protected baseline tests: owner-controlled and immutable to both proposal roles;
- authority/CI paths: readable but not proposal-writable.

Candidate verification requires:

1. protected baseline test files remain byte-identical;
2. all baseline JUnit identities remain present;
3. roadmap acceptance criteria map to required test identities and those identities are observed;
4. candidate tests pass;
5. test evidence records the exact candidate SHA;
6. post-merge evidence records the exact merge SHA.

`quality-gates.json`, `forbidden.json`, `release-state.json` and `roadmap.json` are runtime inputs, not decorative documentation. `authority.md`, `architecture.md` and free-form `forbidden_directions` remain human-readable context; executable restrictions use the structured policy fields and are included in the authority snapshot rather than being falsely presented as machine-understood prose.

## Review is computed

`review.json` is derived from evidence. The runtime computes:

- non-empty authority snapshot;
- unchanged authority digest;
- accepted path policy decisions;
- candidate test result;
- exact candidate-SHA test binding;
- protected baseline file preservation;
- baseline test-identity preservation;
- required acceptance-test identities;
- candidate minimum test count.

Any failed check becomes a blocking finding.

## Recovery is a real process boundary

The crash-recovery conformance case persists a merge-effect intent, performs the merge, intentionally terminates the controller process before writing the receipt, and starts a new Python process.

The new process loads durable state, discovers the already-performed merge by its stable `Effect-Id`, records one receipt, and refuses duplicate effect identities. A second fresh resume is an idempotent no-op.

## Path semantics are part of the contract

Policy matching uses one segment-aware matcher everywhere. `**` means zero or more full path segments, so:

```text
src/security/guard.py
src/reference_app/security/guard.py
```

both match:

```text
src/**/security/**
```

The same matcher is used for write gates, authority snapshots, protected paths and risk rules. No `Path.glob`/`fnmatch` split is used.

## Evidence and schemas

JSON Schema Draft 2020-12 contracts exist for the core public and safety artifacts, including:

- goal and policy;
- plan and durable state;
- policy decision and review;
- candidate and merge evidence;
- test and risk evidence;
- recovery evidence;
- events and terminal summary.

Conformance validates emitted artifacts against those schemas.

The event log is **hash-linked consistency evidence, not a cryptographic authenticity signature**. Someone able to rewrite the whole evidence directory can recompute an unkeyed chain. A production system needs an external or signed anchor.

## Local execution boundary

The showcase executes only built-in **trusted deterministic fixture proposals**. Its local test executor has timeout, environment scrubbing and process resource limits, but it is **not a security sandbox** and does not provide filesystem or network isolation.

The runtime refuses proposal sources other than `trusted-fixture` in this standalone mode.

Do **not** connect an external model or untrusted code producer to this local executor. A production adapter must provide a real sandbox/container/VM boundary before executing untrusted candidate code.

## Validate

```bash
./scripts/agentctl validate
```

This performs non-mutating repository validation, unit tests of control functions and the complete conformance matrix.

## Repository map

```text
reference_runtime/          runtime, matcher, executor, evidence/schema validation
schemas/                    JSON Schema contracts
config/reference-policy.json
examples/minimal-product/   product + product-authored authority
examples/scenarios/         executable conformance fixtures
scripts/agentctl            operator entry point
tests/                      code-path and publication tests
docs/                       architecture, policy, evidence, verification, publication
```

## Origin, license and branding

This reference architecture was originally developed and published from the **Horistum GitHub organization**.

Source code, documentation, schemas and examples are licensed under the **Apache License 2.0**. See `LICENSE` and `NOTICE`.

The Apache-2.0 license does not grant rights to use the **Horistum** name, logos or distinctive branding as the identity of a fork, product or service. See `TRADEMARKS.md`.

Contributions are governed by `CONTRIBUTING.md`; support expectations by `SUPPORT.md`; security reporting by `.github/SECURITY.md`; release rules by `docs/RELEASES.md`.

## What this repository does not claim

It does not claim that deterministic fixture roles are equivalent to a production AI system. It does not claim the local executor is safe for untrusted code. It does not claim the unkeyed event chain proves authenticity.

It demonstrates the surrounding control-plane properties in executable form: bounded authority, independent write domains, exact identity, evidence-based review, risk boundaries, durable state, process recovery and conformance.
