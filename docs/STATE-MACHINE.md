# Durable state machine

Contract v3 persists the phase at every meaningful control boundary.

```text
INITIALIZING
  -> BASELINE_VERIFY
  -> DISCOVERY
  -> PLANNING
  -> PROPOSAL_GATES
  -> CANDIDATE_APPLY
  -> CANDIDATE_COMMIT
  -> CANDIDATE_VERIFY
  -> REVIEW
  -> RISK_GATE
  -> MERGE_PENDING / WAITING_EXTERNAL
  -> POSTMERGE_VERIFY
  -> COMPLETED
```

Terminal alternatives are:

- `BLOCKED_POLICY`
- `FAILED_VERIFICATION`
- `AWAITING_DECISION` with status `NEEDS_DECISION`
- `COMPLETED`

The durable state records run identity, status, phase, base/candidate/merge SHA, risk, pending effect and event tip.

## Recovery boundary

Before merge, the runtime persists a merge intent containing:

- base SHA;
- candidate SHA;
- effect kind;
- stable request hash.

The crash-recovery conformance fixture then:

1. performs the merge effect with `Effect-Id: <request-hash>` in the merge commit;
2. terminates the process before receipt consumption;
3. starts a new Python process;
4. loads persisted state;
5. discovers the existing effect by request identity;
6. verifies exactly one matching merge exists;
7. consumes the effect and continues post-merge verification;
8. starts another fresh resume process and proves it is an idempotent terminal no-op.

This is intentionally different from reading a file back in the same process and calling it recovery.
