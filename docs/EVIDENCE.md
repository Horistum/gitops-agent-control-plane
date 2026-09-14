# Evidence model

## Authority evidence

Authority snapshots enumerate real matching workspace files using the same memoized segment-aware matcher used by write gates. Contract v5 also binds the controller-side `verification-probes.json` by SHA-256 even though that file is deliberately omitted from the candidate workspace.

The runtime fails closed if the workspace authority snapshot or a configured authority pattern matches no file.

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

## Signed controller probe evidence

Standalone verification is recorded in:

```text
probe-baseline.json
probe-negative-control.json
probe-candidate.json
probe-postmerge.json
```

The product authors the probe definition, but it is read from controller-side product source rather than copied into the candidate workspace. Each probe evidence artifact records the verifier-definition digest.

For each probe the controller creates a fresh secret HMAC key and challenge. They are delivered only to a trusted verifier parent through an inherited control FD. They do not appear in argv or environment.

The verifier parent reads and closes the control FD before any candidate child starts. It then generates fresh cases, executes a candidate child for each case, evaluates raw child outcomes against the private oracle and emits one HMAC-SHA256 authenticated receipt.

The controller accepts a probe only when:

1. there is exactly one final receipt line;
2. its HMAC verifies with the controller-held key;
3. challenge and probe identity match;
4. the verifier parent reports protocol completion;
5. all generated cases satisfy the invariant/oracle;
6. the worker exits normally within the execution budget.

Candidate child output is captured by the verifier parent and is not forwarded into the final receipt stream.

## Generated-case evidence

Receipt case rows expose generated inputs only **after execution** for auditability, along with input digests and observed raw outcomes. Candidate and post-merge cases are freshly generated and independent from the baseline negative-control cases.

Probe definitions contain generator/invariant descriptions rather than literal fixed input/expected-result tuples. This makes a lookup table over published fixtures insufficient. It remains randomized testing, not formal proof.

## Negative control

New acceptance properties are first executed against baseline. Negative control is valid only if those generated cases complete and fail against the baseline implementation. Regression/baseline probes are separate and must pass on baseline.

## Candidate review evidence

`review.json` is computed from authority preservation, write policy, protected tests, negative-control result, signed controller-probe result, exact probe SHA binding and supplemental diagnostic status.

Conformance deliberately proves that green forged JUnit, argv nonce forgery and fixed-example overfitting cannot override failing signed probes.

## Effect evidence

Merge intent is persisted before effect execution. Merge commits carry a stable `Effect-Id` as the final non-empty trailer line. Recovery accepts an effect only when that exact trailer identifies one merge commit.

## Event chain: consistency, not authenticity

Events are hash-linked. This detects corruption or edits where hashes are not recomputed.

There is no secret key or external anchor in the standalone event log. A full evidence-directory rewriter can recompute the chain and terminal tip. Production systems need an independent anchor/signature/transparency mechanism.

## JSON Schema

The built-in validator supports an explicit Draft 2020-12 subset and rejects unknown keywords. Scenario fixtures, verifier definitions, diagnostic evidence, signed probe evidence, post-merge evidence and core safety artifacts are schema-validated during conformance.

## Scope boundary

Signed controller probe evidence is authoritative **within the deterministic trusted-fixture scope of this repository**. Same-host malicious Python can still attempt process/kernel/filesystem attacks outside the protocol model. Production hostile-code verification requires a stronger isolation boundary and independently trusted result channel.
