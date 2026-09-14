# Executable showcase

Run:

```bash
./scripts/agentctl conformance
```

Scenarios are discovered from `examples/scenarios/`. The matrix is intentionally heavier on refusals than on the happy path.

## Happy path

`happy-path` demonstrates:

- non-empty authority snapshot including protected verification probes;
- protected baseline tests;
- baseline regression probes;
- acceptance probes that must fail on baseline as a negative control;
- real candidate Git SHA;
- candidate-process JUnit diagnostics;
- controller-owned probe verification bound to the candidate SHA;
- computed review;
- low-risk auto-merge;
- different merge SHA;
- post-merge controller probes bound to the merge SHA.

## Evidence-forgery regressions

`insufficient-tests` gives the tester **the exact expected test method names but empty bodies** while the implementation is wrong. JUnit is green. Controller probes fail and the candidate is rejected.

`assertion-tamper` lets the developer modify a legal `src/**` file that monkeypatches `unittest.TestCase.assertEqual` and `assertRaises` during package import. The diagnostic suite appears green. Controller probes load the target source directly and reject the wrong behavior.

`junit-forgery` gives the tester no acceptance file at all. Developer code monkeypatches `ElementTree.write` and manufactures a five-test green JUnit document containing fictional acceptance identities. The controller records that diagnostic lie but still rejects the candidate because product-authored probes fail.

These scenarios exist specifically to show that JUnit names/counts/XML are no longer an authorization channel.

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
