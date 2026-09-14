# Durable state machine

Contract v5 persists the phase at every meaningful control boundary.

```text
INITIALIZING
  -> BASELINE_VERIFY
       generated baseline probes + generated acceptance negative control
  -> DISCOVERY
  -> PLANNING
  -> PROPOSAL_GATES
  -> CANDIDATE_APPLY
  -> CANDIDATE_COMMIT
  -> CANDIDATE_VERIFY
       HMAC-signed randomized controller probes + diagnostic JUnit
  -> REVIEW
  -> RISK_GATE
  -> MERGE_PENDING / WAITING_EXTERNAL
  -> POSTMERGE_VERIFY
       independently generated signed probes + diagnostics
  -> COMPLETED
```

Terminal alternatives are `BLOCKED_POLICY`, `FAILED_VERIFICATION`, `AWAITING_DECISION` with status `NEEDS_DECISION`, and `COMPLETED`.

Malformed authority/policy configuration, including an empty authority snapshot or disabled mandatory quality gate, is fail-closed and produces terminal `BLOCKED_POLICY` evidence rather than an unstructured traceback.

The durable state records run identity, status, phase, base/candidate/merge SHA, risk, pending effect and event tip. Receipt HMAC keys are ephemeral per-probe values and are deliberately **not** persisted in durable state/evidence.

## Recovery boundary

Before merge, the runtime persists base SHA, candidate SHA, effect kind and stable request hash.

The crash-recovery fixture then:

1. performs the merge with `Effect-Id: <request-hash>` as the exact final non-empty trailer line;
2. terminates the process before receipt consumption;
3. starts a new Python process;
4. revalidates proposal-source and authority contracts;
5. loads persisted state;
6. discovers the existing effect by exact trailer identity;
7. verifies exactly one matching merge exists;
8. consumes the effect and runs fresh post-merge generated probes;
9. starts another fresh resume process and proves it is an idempotent terminal no-op.

This is intentionally different from reading a file back in the same process and calling it recovery.
