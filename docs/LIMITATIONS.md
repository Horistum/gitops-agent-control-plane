# Limitations

The reference is deliberately executable, but it is not a production autonomous engineering runtime.

## No complete hostile-code verifier boundary

Contract v4 removes JUnit from the authoritative acceptance path and introduces product-authored controller probes, negative controls, fresh probe processes and completion receipts.

That is stronger than trusting test names/counts from the candidate process, but it is **not a proof against arbitrary malicious Python code**. The probe process still executes candidate source on the same host and without kernel/container isolation. An adversarial candidate may attempt behavior beyond the protocol assumptions.

For production model-generated code, the verifier must execute across an isolation boundary whose evidence channel the candidate cannot write or impersonate.

## JUnit is diagnostic only

The candidate test process may import code from `src/**`. That code can affect `unittest`, XML serialization or other in-process state. Therefore `test-*.json` and JUnit identities/counts are useful diagnostics but are not authoritative acceptance evidence.

Contract v4 conformance deliberately demonstrates empty test bodies, assertion monkeypatching and JUnit XML forgery while requiring controller probes to reject the wrong implementation.

## No general security sandbox

The local executor is suitable only for deterministic `trusted-fixture` scenarios. Timeouts, CPU/process limits and process-group cleanup are bounded execution controls, not filesystem/network isolation.

## No evidence authenticity anchor

The event chain provides internal consistency only. It does not defeat a party able to rewrite the complete evidence directory and recompute hashes.

## No remote forge/CI proof

Local Git commits and controller probes demonstrate exact-identity mechanics. A production adapter must separately establish remote Git, trusted CI/verifier producer identity, credentials and remote effect semantics.

## Structured authority only

Runtime enforcement reads structured roadmap, forbidden, release-state, quality-gate and verification-probe JSON. `authority.md`, `architecture.md` and free-form goal prose are contextual documentation, not magically executable policy.

## Probe format is intentionally small

The standalone probe worker currently supports direct calls to functions from a single target source file with JSON-representable arguments and expected return values or exception class names. It is an educational portability contract, not a general test framework.

## Reference fixtures are deterministic

They demonstrate controller behavior, not model capability. A future reasoning integration must preserve the same authority boundaries and move hostile-code verification behind stronger isolation rather than assuming the fixture trust model generalizes automatically.
