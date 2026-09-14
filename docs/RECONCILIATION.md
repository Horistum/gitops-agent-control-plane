# Goal reconciliation and repair

At each cycle the controller projects requested, completed, remaining, eligible, and dependency-blocked work. Only requested ready items with satisfied dependencies may be selected.

Candidate verification failure may persist feedback and route a bounded **developer repair** attempt rather than terminating immediately. Attempt and cycle budgets are the minimum of policy and goal authority.

After post-merge verification, release-state advancement is itself a durable controller effect. The controller first persists a `control-state` intent containing the desired release-state digest and stable `Control-State-Id`, then commits `.agent-control/release-state.json`. If the process terminates before receipt/evidence consumption, a fresh process can observe the existing `Control-State-Id` commit, verify the desired state, avoid a duplicate commit, consume the effect, reload authority, and continue goal reconciliation.

Durability also covers crashes **after** an effect receipt has been consumed. `POSTMERGE_VERIFY` can be replayed against the already-recorded exact merge SHA, while `RECONCILE` can continue from controller-recorded release state with no pending side effect. `phase-recovery.json` records which durable phase was resumed and which safe action was taken.

The controller therefore treats both the product merge and the controller-owned release-state transition as recoverable Git effects and also persists safe phase boundaries between them. It stops only when the requested objective is satisfied or when policy/authority prevents further progress.
