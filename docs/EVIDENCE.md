# Evidence model

## Authority evidence

Authority snapshots enumerate real matching files using the exact same memoized segment-aware matcher used by write gates. The runtime fails closed if the authority snapshot or a configured authority pattern matches no file.

## Diagnostic JUnit evidence

`test-baseline.json`, `test-candidate.json` and `test-postmerge.json` record candidate-process diagnostics:

- exact tested Git SHA;
- exit code and timeout flag;
- testcase count and identities;
- failures/errors/skips;
- stdout/stderr digests;
- process-group/resource metadata.

Before each run stale JUnit output is removed.

These artifacts explicitly carry `authoritative: false`. Candidate code is imported by the same Python process that produces JUnit, so test names/counts/XML are not a sufficient authorization channel.

## Controller probe evidence

Authoritative standalone verification is recorded in:

```text
probe-baseline.json
probe-negative-control.json
probe-candidate.json
probe-postmerge.json
```

Probe definitions live in protected product authority, not in the candidate write envelope.

Each required probe:

1. runs in a fresh child process;
2. directly loads the declared target source file rather than the candidate package initializer;
3. uses a controller-generated nonce;
4. must emit a matching completion receipt after protocol completion;
5. records pass/fail plus worker exit/timeout evidence.

A child that merely calls `os._exit(0)` leaves no completion receipt and fails verification.

New acceptance probes are first executed against the baseline. The negative control is valid only if those probes complete and fail there. This prevents empty/tautological acceptance checks from becoming useful evidence merely because their names look correct.

## Candidate review evidence

`review.json` is computed from authority preservation, write policy, protected tests, negative-control result, controller probe result, exact probe SHA binding and supplemental diagnostic status.

Conformance deliberately proves that green forged JUnit evidence cannot override failing controller probes.

## Effect evidence

Merge intent is persisted before effect execution. Merge commits carry a stable `Effect-Id` as the final non-empty trailer line. Recovery accepts an effect only when that exact trailer identifies one merge commit.

## Event chain: consistency, not authenticity

Events are hash-linked. This detects corruption or edits where hashes are not recomputed.

There is no secret key or external anchor in the standalone reference. A full evidence-directory rewriter can recompute the chain and terminal tip. Production systems need an independent anchor/signature/transparency mechanism.

## JSON Schema

The built-in validator supports an explicit Draft 2020-12 subset and rejects unknown keywords. Scenario fixtures, diagnostic test evidence, controller probe evidence, post-merge evidence and the existing core safety artifacts are schema-validated during conformance.

## Scope boundary

Controller probe evidence is authoritative **within the deterministic trusted-fixture scope of this repository**. It is not a cryptographic guarantee against arbitrary hostile Python executing in the same host/process sandbox. Production hostile-code verification requires a stronger isolation boundary and independently trusted result channel.
