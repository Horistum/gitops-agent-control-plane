# GitOps Agent Control Plane Reference

A **standalone executable reference** for policy-bounded autonomous software delivery through Git.

**Initiated and maintained by the Horistum project.**

The current portable contract is `gitops-agent-control-plane/v6`. The reference runs with Bash, Git and Python 3.11+; CI validates Python 3.11, 3.12 and 3.13.

## One-command demo

```bash
./scripts/agentctl demo happy-path
```

A successful run creates a real baseline commit, case-level negative-control evidence, a separate candidate commit, HMAC-authenticated controller verification bound to that candidate SHA, a computed review, a real non-fast-forward merge, independently generated post-merge verification, durable state and evidence.

## Why v6 exists

Full review of v5 found three important gaps:

1. its `nonce-forgery` conformance fixture attacked an obsolete argv protocol and therefore did not exercise the claimed attack;
2. negative control was aggregated at probe level, so one failing case could distinguish a probe even when the baseline already satisfied most generated cases;
3. probe generators/oracles were product-specific Python code in the control plane rather than a reusable product-authored contract.

V6 replaces the stale scenario with a **current-protocol receipt-injection attack**, requires **every generated acceptance case** to fail on the baseline, and introduces a small generic declarative probe DSL.

## Generic probe DSL

`examples/minimal-product/.agent-control/verification-probes.json` is product-authored authority. The controller reads it from the product source and omits it from the candidate workspace.

The DSL supports multiple positional arguments, named kwargs, reusable generator primitives and expression-based return invariants. The example product composes generic operations such as token generation, whitespace splitting, joining and concatenation. The control plane contains no `greet` or `normalize_name` oracle.

Fresh cases are generated independently for baseline regression, negative control, candidate verification and post-merge verification.

## Receipt channel

For each probe, the controller creates a fresh HMAC key and challenge. The trusted verifier parent receives the control payload through an inherited pipe created by the executor. The reader process is started before the payload is written, avoiding pipe-buffer deadlock.

The verifier parent never imports candidate code. Candidate children receive only the current generated args/kwargs. Candidate stdout is captured as untrusted observation and cannot become the controller-facing final receipt. The controller accepts exactly one parent receipt and verifies its HMAC, challenge, probe identity and protocol version.

The `receipt-injection` scenario actually writes a forged final-receipt line from candidate code. Conformance requires evidence that this injection attempt occurred and that the parent receipt channel remained singular and valid.

## Verification layers

- candidate-process JUnit: useful diagnostics, explicitly non-authoritative;
- candidate-child raw outcome: untrusted observation;
- verifier-parent signed receipt: authoritative within the deterministic standalone fixture scope;
- production hostile-code evidence: requires a stronger isolation boundary.

The local executor is **not a security sandbox**. Timeouts, process groups, HMAC and property cases do not replace a container, VM or independently controlled remote verifier for arbitrary malicious/model-generated code.

## Conformance

```bash
./scripts/agentctl conformance
```

Scenarios are discovered from `examples/scenarios/`. The matrix covers the happy path, forbidden writes, baseline-test tampering, failed behavior, empty diagnostic tests, assertion monkeypatching, JUnit forgery, **current receipt injection**, narrow probe-aware overfitting, independent file/byte budgets, risk ceiling, MEDIUM auto-merge boundary, HIGH human gate and cross-process crash recovery.

`probe-aware` is tied to the current contract rather than a historical literal. It implements the public diagnostic example plus a deliberately narrow ASCII subset; the current product-owned `greet-unicode` invariant must reject it.

The matrix also contains `raw-outcome-forgery`, which is intentionally classified as **KNOWN-LIMIT**. It reproduces the acknowledged same-process weakness below the signed-receipt boundary: malicious candidate code can inspect the trusted child-wrapper frame, forge the current `REFERENCE_RAW_OUTCOME`, and terminate before the genuine wrapper observation is emitted. The verifier parent then signs the forged observation. The scenario passes only when this limitation is actually reproduced and its evidence proves the candidate's direct unicode behavior is wrong.

A successful matrix therefore means **all enforced properties behaved as expected and all declared known limits were reproducible**. It does not mean the standalone fixture has no known security limitations. `conformance-report.json` exposes known-limit scenarios separately in `known_limits_reproduced`.

## Evidence and schemas

Core safety evidence is schema-validated, including authority snapshots, protected-test snapshots, merge intent, human-decision artifacts, requests, proposals, role evidence, signed probe receipts and per-case results. The built-in Draft 2020-12 subset is fail-closed on unsupported keywords.

The event log remains hash-linked consistency evidence, not cryptographic authenticity. A production system needs an external or signed anchor.

## Validate

```bash
./scripts/agentctl validate
```

This runs non-mutating repository validation, direct code-path tests and the complete conformance matrix.

## Origin, license and branding

This reference architecture was originally developed and published from the **Horistum GitHub organization**. Source code, documentation, schemas and examples are Apache-2.0 licensed; see `LICENSE` and `NOTICE`. Horistum branding is governed separately by `TRADEMARKS.md`.

## What this repository does not claim

It does not claim deterministic fixtures equal a production AI system, randomized testing is formal proof, same-host execution is hostile-code isolation, or unkeyed hashes prove authenticity.

It demonstrates bounded authority, exact identity, generic product-authored invariants, case-level negative control, signed verifier-parent receipts, evidence-aware review, risk boundaries, durable effects, executable negative conformance and executable known-limit reproduction within the documented standalone trust model.
