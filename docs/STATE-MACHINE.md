# Durable state machine

The concrete standalone runtime uses these persisted phases:

`INITIALIZING → RECONCILE → DISCOVERY → BASELINE_VERIFY → PLANNING → PROPOSAL_GATES → CANDIDATE_APPLY → CANDIDATE_COMMIT → CANDIDATE_VERIFY → REVIEW → RISK_GATE`.

Review failure with remaining budget routes through durable feedback into another bounded `PLANNING` attempt. Human authority may pause at `AWAITING_DECISION` and resume with approve/reject/request_changes.

Approved work then uses two separately durable Git effects:

`MERGE_PENDING → POSTMERGE_VERIFY → CONTROL_STATE_PENDING → RECONCILE`.

`MERGE_PENDING` persists candidate merge intent before the product merge. `CONTROL_STATE_PENDING` persists the desired controller-owned release-state transition before committing it. Either pending effect can be recovered in a fresh process by stable Git trailer identity without duplicating the effect.

There are also safe **phase recovery** checkpoints after effect consumption. A restart in `POSTMERGE_VERIFY` reruns exact-revision post-merge verification; a restart in `RECONCILE` continues goal reconciliation from controller-owned release state. Neither path invents or repeats a Git effect.

From `RECONCILE`, a satisfied goal terminates at `GOAL_COMPLETED`; no dependency-ready authorized work or exhausted autonomy budgets terminate fail-closed.
