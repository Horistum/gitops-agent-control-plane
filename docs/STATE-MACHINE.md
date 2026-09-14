# Durable state machine

`INITIALIZING → BASELINE_VERIFY → RECONCILE_GOAL → DISCOVERY → PLANNING → PROPOSAL_GATES → CANDIDATE_APPLY → CANDIDATE_COMMIT → CANDIDATE_VERIFY → REVIEW`.

Review failure with remaining budget routes to `FEEDBACK → PLANNING`. Accepted work proceeds to `RISK_GATE`; human authority may pause at `AWAITING_DECISION` and resume with approve/reject/request_changes.

Approved work goes through two separately durable Git effects:

`MERGE_PENDING → POSTMERGE_VERIFY → CONTROL_STATE_PENDING → RECONCILE → RECONCILE_GOAL`.

`MERGE_PENDING` persists the candidate merge intent before the product merge. `CONTROL_STATE_PENDING` persists the desired controller-owned release-state transition before committing it. Either pending effect can be recovered in a fresh process by stable Git trailer identity without duplicating the effect.

There are also safe **phase recovery** checkpoints after effect consumption. A restart in `POSTMERGE_VERIFY` reruns exact-revision post-merge verification; a restart in `RECONCILE` continues goal reconciliation from controller-owned release state. Neither path invents or repeats a Git effect.

Goal satisfaction terminates at `GOAL_COMPLETED`; unsatisfied dependency authority or exhausted budgets terminate fail-closed.
