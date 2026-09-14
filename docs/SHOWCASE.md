# Executable showcase

Run:

```bash
./scripts/agentctl conformance
```

Scenarios are discovered from `examples/scenarios/`. The matrix is intentionally heavier on refusals than on the happy path.

## Happy path

`happy-path` demonstrates:

- non-empty workspace authority snapshot plus controller-side verifier-definition digest;
- verifier definition absent from the candidate workspace;
- protected baseline tests;
- generated baseline regression probes;
- generated acceptance probes that must fail on baseline as a negative control;
- real candidate Git SHA;
- candidate-process JUnit diagnostics;
- HMAC-authenticated single verifier-parent receipts;
- fresh candidate cases bound to the candidate SHA;
- computed review;
- low-risk auto-merge;
- different merge SHA;
- independently generated post-merge probes bound to the merge SHA.

## Evidence-forgery regressions

`insufficient-tests` gives the tester the expected test method names but empty bodies while the implementation is wrong. JUnit is green. Signed controller probes fail.

`assertion-tamper` lets developer code monkeypatch `unittest` during diagnostic package import. Diagnostic JUnit is green. The trusted verifier parent never imports candidate code and rejects the wrong behavior.

`junit-forgery` gives the tester no acceptance file. Developer code manufactures a five-test green JUnit document. Signed probes still reject the implementation.

`nonce-forgery` implements the previous argv attack: it looks for `--nonce` and `--probe-json`, attempts to print a fake success receipt and exits. Contract v5 puts neither secret nor probe JSON in candidate argv. The final receipt is created by the verifier parent and HMAC-authenticated, so the attack fails.

## Oracle-overfitting regression

`probe-aware` implements only the old public examples: `Ada Lovelace` and blank input. Classic acceptance JUnit therefore passes.

The verifier definition no longer publishes fixed tuples and is omitted from the candidate workspace. The verifier parent generates fresh random name/whitespace cases after candidate creation and evaluates the greeting invariant. The lookup-table implementation fails those cases and is rejected.

This scenario distinguishes **receipt-channel integrity** from **oracle strength**. Both matter.

## Other negative authority and verification cases

`forbidden-path` tries to modify product authority and is blocked before a candidate side effect.

`test-tamper` tries to modify the protected baseline test file from the developer role and is blocked by actor-specific write policy.

`test-failure` uses honest diagnostic tests against a deliberately broken implementation; both diagnostics and controller probes fail.

## Policy reachability

`budget-exceeded` crosses the configured changed-file budget before mutation.

`patch-budget-exceeded` stays within file-count limits but exceeds patch bytes.

`risk-ceiling` touches a HIGH path under a goal limited to MEDIUM authority and is blocked before mutation.

`medium-auto-boundary` reaches MEDIUM risk while the LOW auto-merge ceiling independently forces `NEEDS_DECISION`.

`human-gate` touches top-level `src/security/guard.py`; `src/**/security/**` correctly matches zero intermediate segments and requires human authority.

## Crash recovery

`crash-recovery` performs a real process termination after the merge effect and before receipt persistence. A new process recovers the pending effect by exact final `Effect-Id` trailer and verifies there is only one matching merge.

The harness retains failure evidence and continues later scenarios if one scenario fails.
