# Limitations

The reference is deliberately executable, but it is not a production autonomous engineering runtime.

## No complete hostile-code verifier boundary

Contract v5 removes verifier secrets from candidate argv/environment, moves candidate execution into child processes below a trusted verifier parent, signs final receipts and stops copying verifier definitions into the candidate workspace.

That closes concrete protocol mistakes. It is still **not a proof against arbitrary malicious Python code** on the same host. A malicious same-user process may attempt `/proc` inspection, kernel/process attacks, filesystem discovery or other behavior outside the protocol assumptions.

For production model-generated code, the verifier must execute across an isolation boundary whose evidence channel the candidate cannot write or impersonate.

## Randomized properties are tests, not proof

Contract v5 replaces published fixed input/expected-result tuples with generated cases and invariants. This prevents simple lookup-table overfitting to known probe fixtures.

It does not prove correctness for every input. A finite randomized sample can miss defects. Production systems should combine property generation with deterministic regression suites, static analysis, domain-specific checks and, where appropriate, formal verification.

## Candidate sees its current input

A candidate child necessarily receives the current function input being tested. It does **not** receive the private oracle, future generated cases, HMAC key or receipt challenge through the normal protocol.

A candidate that generically computes the correct result for the current input is satisfying the observable property. The reference does not attempt to distinguish a legitimate implementation from an implementation that arrives at the same black-box result by an unusual internal method.

## JUnit is diagnostic only

The candidate test process may import code from `src/**`. That code can affect `unittest`, XML serialization or other in-process state. Therefore `test-*.json` and JUnit identities/counts are useful diagnostics but are not authoritative acceptance evidence.

Conformance deliberately demonstrates empty test bodies, assertion monkeypatching and JUnit XML forgery while requiring signed controller probes to reject the wrong implementation.

## Probe definition visibility outside workspace

`verification-probes.json` is omitted from the candidate workspace, but it remains versioned in the same repository and is therefore not a cryptographic secret. On the standalone same-host fixture a sufficiently adversarial process might search outside its workspace.

Security comes from fresh generated inputs plus the private receipt key, not from pretending the probe source file is secret. Production isolation must prevent candidate access to verifier internals when that matters.

## No general security sandbox

The local executor is suitable only for deterministic `trusted-fixture` scenarios. Timeouts, CPU/process limits and process-group cleanup are bounded execution controls, not filesystem/network isolation.

## No evidence authenticity anchor

The event chain provides internal consistency only. It does not defeat a party able to rewrite the complete evidence directory and recompute hashes.

## No remote forge/CI proof

Local Git commits and signed controller probes demonstrate exact-identity mechanics. A production adapter must separately establish remote Git, trusted CI/verifier producer identity, credentials and remote effect semantics.

## Structured authority only

Runtime enforcement reads structured roadmap, forbidden, release-state, quality-gate and verification-probe JSON. `authority.md`, `architecture.md` and free-form goal prose are contextual documentation, not magically executable policy.

## Probe protocol is intentionally small

The standalone property verifier supports a small registry of generators and oracles for the minimal reference product. Unsupported generators, oracle kinds and exception names are configuration errors rather than silently degraded checks.

It is a portability demonstration, not a general property-testing framework.

## Reference fixtures are deterministic

They demonstrate controller behavior, not model capability. A future reasoning integration must preserve the same authority boundaries and move hostile-code verification behind stronger isolation rather than assuming the fixture trust model generalizes automatically.
