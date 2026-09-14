# Executable showcase

Run:

```bash
./scripts/agentctl conformance
```

Scenarios are discovered from `examples/scenarios/`. Negative cases are expected to prove their attack path, not merely end in a red status.

## Happy path

`happy-path` demonstrates non-empty authority evidence, protected tests, baseline regressions, **every-case** acceptance negative control, real candidate SHA, non-authoritative JUnit diagnostics, HMAC-authenticated verifier-parent receipts, generic product-authored invariants, computed review, low-risk merge, distinct merge SHA and fresh post-merge verification.

## Evidence-forgery regressions

`insufficient-tests`, `assertion-tamper` and `junit-forgery` keep diagnostic evidence green/plausible while controller verification rejects wrong behavior.

`receipt-injection` attacks the **current protocol**. Candidate code writes a fake `REFERENCE_PROBE_RECEIPT=` line to its own stdout during import. The verifier parent records `candidate_receipt_injection_count`; conformance requires that count to be non-zero and simultaneously requires exactly one valid controller-facing parent receipt. A scenario where the attack path never executes therefore fails conformance.

## Oracle-overfitting regression

`probe-aware` implements the public diagnostic example and a deliberately narrow two-token ASCII behavior. It is not coupled to an obsolete historical probe literal. Current product authority additionally requires `greet-unicode`; every generated case for that invariant must fail for the narrow implementation.

The scenario therefore demonstrates the current contract: public diagnostics can pass while a broader product-owned property rejects overfitting.

## Negative-control strength

Acceptance negative control is evaluated per generated case. If baseline satisfies even one generated acceptance case, the negative control fails. Regression probes are separate and must pass on baseline.

## Other policy/recovery cases

The matrix also exercises forbidden authority writes, protected-test tampering, genuine implementation failure, independent file/patch budgets, risk ceiling, MEDIUM auto-merge boundary, HIGH human gate and real process crash recovery using exact `Effect-Id` identity.

The harness keeps running after individual failures and retains structured evidence/reporting for every scenario.
