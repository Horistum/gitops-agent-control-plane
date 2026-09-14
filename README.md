# GitOps Agent Control Plane Reference

A **standalone executable reference** for policy-bounded autonomous software delivery through Git.

**Initiated and maintained by the Horistum project.**

This repository demonstrates control-plane mechanics, not a production AI product. The current portable contract is `gitops-agent-control-plane/v4`.

The reference runs with **Bash, Git and Python 3.11+**. CI executes the same contract on Python 3.11, 3.12 and 3.13.

## One-command demo

```bash
./scripts/agentctl demo happy-path
```

A successful run creates a real baseline commit, negative-control evidence, a separate candidate commit, controller-owned verification bound to that candidate SHA, a computed review, a real non-fast-forward merge, post-merge verification bound to the merge SHA, durable state and audit evidence.

Evidence is written under `.demo/runs/<run-id>/evidence/`.

## Why v4 exists

Candidate-process JUnit is not a trustworthy authorization channel by itself. Candidate code can execute inside the same Python process as tests and can influence assertions, imports or XML serialization.

Contract v4 therefore distinguishes:

- **diagnostic JUnit**: useful visibility, explicitly non-authoritative;
- **controller probes**: product-authored structured checks under `.agent-control/verification-probes.json`;
- **negative control**: new acceptance probes must fail against the baseline implementation before a candidate can use them as evidence;
- **completion receipt**: every probe runs in a fresh process and must return a controller-recognized nonce-bound receipt; `exit(0)` alone is not success;
- **exact Git binding**: candidate and post-merge probe evidence records the exact SHA being observed.

This is a stronger reference protocol, but it is still not a complete hostile-code sandbox. Production model-generated code requires a verifier behind a stronger isolation boundary.

## Conformance is more important than the happy path

```bash
./scripts/agentctl conformance
```

Scenarios are discovered from `examples/scenarios/`. Contract v4 includes the existing lifecycle/risk/recovery cases plus three direct evidence-forgery regressions:

| Scenario | Expected terminal state | Property |
|---|---|---|
| `happy-path` | `COMPLETED` | full bounded lifecycle with negative control and controller probes |
| `forbidden-path` | `BLOCKED_POLICY` | authority rewrite rejected before candidate side effect |
| `test-tamper` | `BLOCKED_POLICY` | developer cannot replace protected baseline tests |
| `test-failure` | `FAILED_VERIFICATION` | wrong behavior fails diagnostic tests and controller probes |
| `insufficient-tests` | `FAILED_VERIFICATION` | correct test names with empty bodies cannot manufacture acceptance |
| `assertion-tamper` | `FAILED_VERIFICATION` | monkeypatched `unittest` assertions cannot manufacture controller evidence |
| `junit-forgery` | `FAILED_VERIFICATION` | forged five-test XML cannot authorize a wrong candidate |
| `budget-exceeded` | `BLOCKED_POLICY` | changed-file budget blocks before workspace mutation |
| `patch-budget-exceeded` | `BLOCKED_POLICY` | patch-byte budget is independently reachable |
| `risk-ceiling` | `BLOCKED_POLICY` | effective risk may exceed owner goal authority |
| `medium-auto-boundary` | `NEEDS_DECISION` | MEDIUM risk and auto-merge ceiling are independent |
| `human-gate` | `NEEDS_DECISION` | top-level `src/security/**` is classified HIGH |
| `crash-recovery` | `COMPLETED` | a fresh process recovers an already-performed merge effect without duplicating it |

A scenario failure does not abort the matrix. Remaining scenarios continue and `conformance-report.json` plus run evidence are retained.

## Authority and write domains

Product-authored authority lives under `examples/minimal-product/.agent-control/`.

The standalone policy separates developer source writes, tester diagnostic-test writes, protected baseline tests and authority/CI paths. `verification-probes.json`, `quality-gates.json`, `forbidden.json`, `release-state.json` and `roadmap.json` are executable structured inputs.

`authority.md`, `architecture.md` and free-form `forbidden_directions` are included in the authority snapshot but remain human-readable context rather than silently machine-interpreted natural language.

## Review is computed

`review.json` is derived from observable controller state. It checks authority preservation, bounded paths, protected tests, baseline negative control, controller probe results, exact candidate-SHA probe binding and supplemental diagnostic JUnit status.

A green JUnit file cannot override a failing controller probe.

## Path and execution bounds

Policy matching uses one memoized segment-aware matcher everywhere. `**` means zero or more complete path segments, including zero, without exponential recursive backtracking.

The local executor uses a policy-derived timeout/CPU budget and a dedicated process group. Descendant processes are cleaned up on timeout and after the direct child exits.

These are bounded-execution controls, **not a security sandbox**.

## Evidence and schemas

The repository validates goal, policy, scenario, state, decision, review, test, probe, effect, recovery and terminal evidence against a fail-closed supported subset of JSON Schema Draft 2020-12. Unsupported schema keywords are rejected instead of ignored.

The event log is hash-linked consistency evidence, not cryptographic authenticity. A production system needs an external or signed anchor.

## Validate

```bash
./scripts/agentctl validate
```

This runs non-mutating repository validation, direct unit tests over control functions and the complete conformance matrix.

## Origin, license and branding

This reference architecture was originally developed and published from the **Horistum GitHub organization**.

Source code, documentation, schemas and examples are licensed under the **Apache License 2.0**. See `LICENSE` and `NOTICE`. The license does not grant rights to use the **Horistum** name, logos or distinctive branding as the identity of a fork, product or service. See `TRADEMARKS.md`.

Contributions are governed by `CONTRIBUTING.md`; support expectations by `SUPPORT.md`; security reporting by `.github/SECURITY.md`; release rules by `docs/RELEASES.md`.

## What this repository does not claim

It does not claim deterministic fixture roles are equivalent to a production AI system. It does not claim the local executor/probe worker is safe against arbitrary malicious code. It does not claim unkeyed event hashes prove authenticity.

It demonstrates bounded authority, exact identity, controller-observed verification, negative controls, evidence-aware review, risk boundaries, durable state, process recovery and conformance within the explicitly documented standalone trust model.
