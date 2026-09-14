# Verification

The current portable contract is:

```text
gitops-agent-control-plane/v5
```

## `./scripts/agentctl validate`

Validation is executable and non-mutating with respect to the example source tree.

It performs:

1. publication/licensing checks;
2. fail-closed JSON Schema loading plus static goal/policy/scenario/probe-definition validation;
3. authority-layout validation using the same path matcher as runtime gates;
4. Python and shell syntax checks;
5. example baseline diagnostics in a temporary copy;
6. unit tests over matcher complexity, risk, active quality gates, private receipt channels, process-group cleanup, stale-JUnit handling, effect trailers, schema keyword rejection, event-chain boundaries and harness failure behavior;
7. the full conformance matrix.

## Supported Python range

GitHub Actions executes validation on Python 3.11, 3.12 and 3.13.

The policy matcher is implemented by the reference, uses memoized segment states and does not delegate `**` semantics to interpreter-dependent `Path.glob` behavior.

## Controller-side verification definition

The product authors the verifier definition at:

```text
examples/minimal-product/.agent-control/verification-probes.json
```

That source file is versioned product authority, but contract v5 does **not copy it into the candidate workspace**. Runtime authority evidence records its controller-side digest separately.

Probe definitions contain generators and invariants, not fixed public argument/expected-result tuples. Example invariant families include randomized whitespace/name normalization, greeting-format properties, and exception properties for blank/non-string inputs.

## Runtime-generated cases

Fresh random cases are generated independently for:

1. baseline regression verification;
2. acceptance negative control on the baseline;
3. candidate verification;
4. post-merge verification.

A candidate therefore cannot pass merely by hardcoding the examples published in README/tests/earlier probe revisions. The `probe-aware` conformance scenario demonstrates this directly: classic fixed-example JUnit is green while fresh randomized invariant cases fail.

## Receipt protocol

For each probe the controller:

1. creates a fresh 256-bit HMAC receipt key and random challenge;
2. writes key, challenge and probe definition into an anonymous pipe;
3. passes only the read side as an inherited **control FD** to a trusted verifier-parent process;
4. places no receipt key/challenge/probe JSON in worker argv or environment;
5. the verifier parent reads and closes the control FD before starting any candidate child;
6. each candidate child receives only its current generated input and writes a raw outcome to a private parent-captured channel;
7. the verifier parent evaluates the raw outcome against its oracle;
8. the verifier parent emits exactly one final receipt authenticated with HMAC-SHA256;
9. the controller requires exactly one receipt line and verifies HMAC, challenge and probe identity.

Candidate stdout from the child is not forwarded into the final receipt channel. `os._exit(0)` without a raw outcome therefore cannot manufacture completion, and the old `--nonce` argv forgery no longer has a secret to read.

## Authoritative verification path

For an authorized roadmap item the controller:

1. runs protected baseline probes and requires them to pass;
2. runs acceptance probes against the baseline and requires them to fail as a negative control;
3. creates the candidate;
4. runs required property probes against the exact candidate SHA;
5. verifies signed receipts;
6. computes review from those results plus policy/authority checks;
7. repeats freshly generated probes after merge against the exact merge SHA.

Candidate-process JUnit remains visible but is **diagnostic and not authoritative**.

## Conformance scenarios

The matrix is discovered from `examples/scenarios/`. In addition to lifecycle/risk/recovery behavior, it contains direct evidence/oracle regressions:

- correct acceptance test names with empty bodies;
- `unittest` assertion monkeypatching;
- forged five-test JUnit;
- the former nonce-from-argv receipt forgery;
- a probe-aware implementation that only satisfies public fixed examples.

The latter two are important distinctions: one attacks the receipt channel, while the other attacks oracle predictability.

The harness catches individual scenario failures, continues remaining scenarios and persists `conformance-report.json` plus run evidence.

## Schema validation

The repository implements an explicit subset of Draft 2020-12. Supported keywords are whitelisted. Adding an unsupported keyword is a hard validation error rather than a silently ignored constraint.

Scenario fixtures, generated probe definitions and emitted safety artifacts are validated against repository schemas plus semantic runtime checks.

## What verification does not prove

It does not prove that:

- same-host candidate Python is safe against arbitrary hostile/model-generated code;
- randomized property checks prove correctness for every possible input;
- the standalone process boundary is equivalent to a VM/container/remote isolated verifier;
- the unkeyed event chain is authentic against a full evidence-directory rewriter;
- a remote Git provider or external CI integration is configured safely.

Randomized invariants make fixture overfitting substantially harder; they are still tests, not a formal proof. Production hostile-code verification must cross a stronger isolation boundary whose result channel the candidate cannot write or impersonate.
