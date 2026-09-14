# Verification

The current portable contract is:

```text
gitops-agent-control-plane/v4
```

## `./scripts/agentctl validate`

Validation is executable and non-mutating with respect to the example source tree.

It performs:

1. publication/licensing checks;
2. fail-closed JSON Schema loading plus static goal/policy/scenario validation;
3. authority-layout validation using the same path matcher as runtime gates;
4. Python and shell syntax checks;
5. example baseline diagnostics in a temporary copy;
6. unit tests over matcher complexity, risk, active quality gates, probe receipts, process-group cleanup, stale-JUnit handling, effect trailers, schema keyword rejection, event-chain boundaries and harness failure behavior;
7. the full conformance matrix.

## Supported Python range

GitHub Actions executes validation on Python 3.11, 3.12 and 3.13.

The policy matcher is implemented by the reference, uses memoized segment states and does not delegate `**` semantics to interpreter-dependent `Path.glob` behavior.

## Authoritative verification path

The v4 standalone trust model uses structured probes from:

```text
examples/minimal-product/.agent-control/verification-probes.json
```

For an authorized roadmap item the controller:

1. runs protected baseline probes and requires them to pass;
2. runs acceptance probes against the baseline and requires them to fail as a negative control;
3. creates the candidate;
4. runs each required baseline/acceptance probe in its own fresh process against the exact candidate SHA;
5. requires a nonce-bound completion receipt for every probe;
6. computes review from those results plus policy/authority checks;
7. repeats the probes after merge against the exact merge SHA.

Candidate-process JUnit remains visible but is **diagnostic and not authoritative**.

## Conformance scenarios

The matrix is discovered from `examples/scenarios/` and includes, among the normal lifecycle/risk/recovery cases, three direct evidence-forgery regressions:

- correct acceptance test names with empty test bodies;
- developer code monkeypatching `unittest` assertions during package import;
- developer code forging a five-test JUnit file while no acceptance-test file exists.

All three fixtures intentionally make diagnostic test evidence look green or plausible while the behavior is wrong. They are conformant only when controller probes reject the candidate.

The matrix also covers forbidden paths, baseline-test tampering, real executable failure, changed-file and patch-byte budgets, goal risk ceiling, MEDIUM auto-merge boundary, HIGH human gate and cross-process merge recovery.

The harness catches individual scenario failures, continues remaining scenarios and persists `conformance-report.json` plus run evidence.

## Schema validation

The repository implements an explicit subset of Draft 2020-12. Supported keywords are whitelisted. Adding an unsupported keyword is a hard validation error rather than a silently ignored constraint.

Scenario fixtures have their own schema, and emitted safety artifacts include schemas for controller-probe evidence and post-merge evidence in addition to the existing goal/policy/review/state/effect artifacts.

## What verification does not prove

It does not prove that:

- the local probe worker is safe against arbitrary hostile/model-generated code;
- process-level controller probes are equivalent to a VM/container/remote isolated verifier;
- the unkeyed event chain is authentic against a full evidence-directory rewriter;
- a remote Git provider or external CI integration is configured safely;
- deterministic fixture roles have the capabilities of a production reasoning model.

Those boundaries are explicit. Production hostile-code verification must cross a stronger isolation boundary whose result channel the candidate cannot write or impersonate.
