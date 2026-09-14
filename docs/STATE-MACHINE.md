# Durable state machine

Contract v6 persists phase at each meaningful control boundary.

```text
INITIALIZING
  -> BASELINE_VERIFY
       regression probes + every-case acceptance negative control
  -> DISCOVERY
  -> PLANNING
  -> PROPOSAL_GATES
  -> CANDIDATE_APPLY
  -> CANDIDATE_COMMIT
  -> CANDIDATE_VERIFY
       generic generated probes + diagnostic JUnit
  -> REVIEW
  -> RISK_GATE
  -> MERGE_PENDING / WAITING_EXTERNAL
  -> POSTMERGE_VERIFY
       fresh generated probes + diagnostics
  -> COMPLETED
```

Terminal alternatives are `BLOCKED_POLICY`, `FAILED_VERIFICATION`, `NEEDS_DECISION`/`AWAITING_DECISION`, and `COMPLETED`.

Malformed authority/policy/probe configuration fails closed. HMAC receipt keys/challenges are ephemeral per probe and are deliberately not persisted in durable state or evidence.

## Recovery boundary

Before merge, the runtime persists base SHA, candidate SHA, effect kind and stable request hash in schema-validated `merge-intent.json`. Crash recovery performs the merge effect, terminates before receipt consumption, starts a new controller process, reloads durable state, finds the existing merge by exact final `Effect-Id` trailer, consumes it once and runs fresh post-merge probes.

A second resume is an idempotent terminal no-op.
