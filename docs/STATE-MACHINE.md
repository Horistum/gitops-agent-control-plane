# Durable state machine

`INITIALIZING → BASELINE_VERIFY → RECONCILE_GOAL → DISCOVERY → PLANNING → PROPOSAL_GATES → CANDIDATE_APPLY → CANDIDATE_COMMIT → CANDIDATE_VERIFY → REVIEW`.

Review failure with remaining budget routes to `FEEDBACK → PLANNING`. Accepted work proceeds to `RISK_GATE`; human authority may pause at `AWAITING_DECISION` and resume with approve/reject/request_changes. Approved work goes through `MERGE_PENDING → POSTMERGE_VERIFY → RELEASE_STATE → RECONCILE_GOAL`. Goal satisfaction terminates at `GOAL_COMPLETED`; unsatisfied dependency authority can terminate at `RECONCILIATION_BLOCKED`.
