# Executable showcase

Run:

```bash
./scripts/agentctl conformance
```

Scenarios are discovered from `examples/scenarios/`. Negative cases are expected to prove their attack path, not merely end in a red status. Known limitations are also executable and are reported separately from enforced properties.

## Happy path

`happy-path` demonstrates non-empty authority evidence, protected tests, baseline regressions, **every-case** acceptance negative control, real candidate SHA, non-authoritative JUnit diagnostics, HMAC-authenticated verifier-parent receipts, generic product-authored invariants, computed review, low-risk merge, distinct merge SHA and fresh post-merge verification.

## Evidence-forgery regressions

`insufficient-tests`, `assertion-tamper` and `junit-forgery` keep diagnostic evidence green/plausible while controller verification rejects wrong behavior.

`receipt-injection` attacks the **current protocol**. Candidate code writes a fake `REFERENCE_PROBE_RECEIPT=` line to its own stdout during import. The verifier parent records `candidate_receipt_injection_count`; conformance requires that count to be non-zero and simultaneously requires exactly one valid controller-facing parent receipt. A scenario where the attack path never executes therefore fails conformance.

## Executable raw-outcome known limit

`raw-outcome-forgery` deliberately attacks the lower observation channel that remains inside the acknowledged same-process boundary. Candidate code walks the trusted `probe_child.py` stack, recovers the current payload and callable, emits a forged `REFERENCE_RAW_OUTCOME=` with `candidate_forged: true`, and calls `os._exit(0)` before the trusted wrapper can report the actual result.

The scenario is intentionally expected to reach `COMPLETED`: it demonstrates that the verifier parent can be fed a forged raw observation and then sign it. Conformance only accepts the scenario when all candidate probe cases carry the candidate-forged marker **and** an independent direct execution proves the candidate's unicode behavior is actually wrong.

This row is displayed as `KNOWN-LIMIT`, not `PASS`. `conformance-report.json` lists it under `known_limits_reproduced`. If the implementation later blocks the attack, the scenario must be converted to an enforced negative case rather than silently disappearing.

## Oracle-overfitting regression

`probe-aware` implements the public diagnostic example and a deliberately narrow two-token ASCII behavior. It is not coupled to an obsolete historical probe literal. Current product authority additionally requires `greet-unicode`; every generated case for that invariant must fail for the narrow implementation.

The scenario therefore demonstrates the current contract: public diagnostics can pass while a broader product-owned property rejects overfitting.

## Negative-control strength

Acceptance negative control is evaluated per generated case. If baseline satisfies even one generated acceptance case, the negative control fails. Regression probes are separate and must pass on baseline.

## Other policy/recovery cases

The matrix also exercises forbidden authority writes, protected-test tampering, genuine implementation failure, independent file/patch budgets, risk ceiling, MEDIUM auto-merge boundary, HIGH human gate and real process crash recovery using exact `Effect-Id` identity.

The harness keeps running after individual failures and retains structured evidence/reporting for every scenario.
