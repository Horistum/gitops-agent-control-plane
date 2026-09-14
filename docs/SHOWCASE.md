# Executable showcase

Run:

```bash
./scripts/agentctl conformance
```

The matrix contains ten scenarios because a control plane is defined at least as much by what it refuses as by what it completes.

## Happy path

`happy-path` proves:

- non-empty authority snapshot;
- protected baseline tests;
- independent acceptance-test write domain;
- real candidate Git SHA;
- five executable tests;
- computed review;
- exact candidate test binding;
- low-risk auto-merge;
- different merge SHA;
- post-merge verification.

## Negative authority and verification cases

`forbidden-path` tries to modify product authority and is blocked before a candidate side effect.

`test-tamper` tries to modify the protected baseline test file from the developer role and is blocked by actor-specific write policy.

`test-failure` uses correct independent acceptance tests against a deliberately broken implementation and fails executable verification.

`insufficient-tests` supplies a green tautological acceptance file. Baseline tests remain present, but the required roadmap acceptance identities are absent, so computed review blocks the candidate.

## Policy reachability

`budget-exceeded` crosses the configured changed-file budget and is blocked before workspace mutation.

`risk-ceiling` touches a HIGH path under a goal overridden to MEDIUM authority and is blocked before workspace mutation.

`medium-auto-boundary` touches a MEDIUM contract path. Human-gate threshold remains HIGH, but the LOW auto-merge ceiling independently forces `NEEDS_DECISION`.

`human-gate` touches top-level `src/security/guard.py`. The segment-aware `src/**/security/**` rule correctly matches it and requires human authority.

## Crash recovery

`crash-recovery` performs a real process termination after the merge effect and before receipt persistence. A new process recovers the pending effect by stable identity and verifies there is only one matching merge.

The harness retains failure evidence and continues later scenarios if one scenario fails.
