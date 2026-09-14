# GitOps Agent Control Plane Reference

A **standalone executable reference** for policy-bounded autonomous software delivery through Git.

**Initiated and maintained by the Horistum project.**

This repository demonstrates control-plane mechanics, not a production AI product. The current portable contract is `gitops-agent-control-plane/v5`.

The reference runs with **Bash, Git and Python 3.11+**. CI executes the same contract on Python 3.11, 3.12 and 3.13.

## One-command demo

```bash
./scripts/agentctl demo happy-path
```

A successful run creates a real baseline commit, generated negative-control evidence, a separate candidate commit, signed controller-owned verification bound to that candidate SHA, a computed review, a real non-fast-forward merge, independently generated post-merge verification bound to the merge SHA, durable state and audit evidence.

Evidence is written under `.demo/runs/<run-id>/evidence/`.

## Why v5 exists

Contract v4 correctly stopped treating JUnit as authoritative, but its probe protocol still had two avoidable weaknesses:

1. the receipt nonce/probe JSON were visible in worker argv to candidate code imported in that same process;
2. probe inputs and literal expected values were public and fixed, allowing a candidate to overfit a lookup table to the published examples.

Contract v5 changes both boundaries.

### Private signed receipt channel

For every probe the controller creates a fresh HMAC key and challenge and sends them to a trusted verifier parent over an inherited anonymous **control FD**. They are absent from argv and environment. The verifier parent reads and closes the FD before starting candidate code and never imports the candidate itself.

Candidate code runs in a separate child process. Child stdout is captured by the verifier parent, not forwarded as the final receipt stream. The controller accepts exactly one final receipt and verifies its HMAC, challenge and probe identity.

### Generated property probes

`verification-probes.json` no longer contains fixed `args`/literal expected returns. It declares case generators plus invariants. Fresh random cases are generated independently for baseline checks, negative control, candidate verification and post-merge verification.

For the minimal product this includes properties such as:

```text
normalize_name(x) == " ".join(x.split())
greet(x) == "Hello, " + " ".join(x.split()) + "!"
```

plus randomized blank and non-string exception cases.

The probe definition is versioned product authority but is **not copied into the candidate workspace**. Runtime evidence binds its controller-side digest separately.

Candidate-process JUnit remains useful diagnostics, explicitly non-authoritative.

## Conformance is more important than the happy path

```bash
./scripts/agentctl conformance
```

Scenarios are discovered from `examples/scenarios/`. Contract v5 includes lifecycle/risk/recovery cases plus direct evidence/oracle attacks:

| Scenario | Expected terminal state | Property |
|---|---|---|
| `happy-path` | `COMPLETED` | full bounded lifecycle with generated negative control and signed probes |
| `forbidden-path` | `BLOCKED_POLICY` | authority rewrite rejected before candidate side effect |
| `test-tamper` | `BLOCKED_POLICY` | developer cannot replace protected baseline tests |
| `test-failure` | `FAILED_VERIFICATION` | wrong behavior fails diagnostics and controller probes |
| `insufficient-tests` | `FAILED_VERIFICATION` | correct test names with empty bodies cannot manufacture acceptance |
| `assertion-tamper` | `FAILED_VERIFICATION` | monkeypatched `unittest` assertions cannot manufacture controller evidence |
| `junit-forgery` | `FAILED_VERIFICATION` | forged five-test XML cannot authorize a wrong candidate |
| `nonce-forgery` | `FAILED_VERIFICATION` | old argv nonce/receipt forgery has no secret to read or receipt channel to inject |
| `probe-aware` | `FAILED_VERIFICATION` | implementation overfit to public fixed examples fails fresh generated invariant cases |
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

The verifier definition is read from the controller-side product source and omitted from the candidate copy. Human-readable `authority.md`, `architecture.md` and free-form `forbidden_directions` remain context rather than silently machine-interpreted natural language.

## Review is computed

`review.json` is derived from observable controller state. It checks authority preservation, bounded paths, protected tests, generated baseline negative control, signed controller probe results, exact candidate-SHA binding and supplemental diagnostic JUnit status.

A green JUnit file cannot override a failing controller probe.

## Path and execution bounds

Policy matching uses one memoized segment-aware matcher everywhere. `**` means zero or more complete path segments, including zero, without exponential recursive backtracking.

The local executor uses a policy-derived timeout/CPU budget and a dedicated process group. Descendant processes are cleaned up on timeout and after the direct child exits.

These are bounded-execution controls, **not a security sandbox**.

## Remaining trust boundary

Randomized invariants prevent simple fixture lookup-table overfitting, and HMAC/control-FD receipts close the previous distributed-secret mistake. They do not make same-host Python adversarially safe.

For arbitrary model-generated or malicious code, production verification must use a container/VM/remote verifier whose filesystem/process boundary and result channel are outside candidate control.

## Evidence and schemas

The repository validates goal, policy, scenario, verification definition, state, decision, review, diagnostic test, signed probe, effect, recovery and terminal evidence against a fail-closed supported subset of JSON Schema Draft 2020-12. Unsupported schema keywords are rejected instead of ignored.

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

It does not claim deterministic fixture roles are equivalent to a production AI system. It does not claim the local executor/verifier is safe against arbitrary malicious code. It does not claim randomized testing is a formal proof. It does not claim unkeyed event hashes prove authenticity.

It demonstrates bounded authority, exact identity, private signed verifier receipts, runtime-generated property checks, negative controls, evidence-aware review, risk boundaries, durable state, process recovery and conformance within the explicitly documented standalone trust model.
