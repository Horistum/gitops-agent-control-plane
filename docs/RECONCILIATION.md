# Goal reconciliation and repair

At each cycle the controller projects requested, completed, remaining, eligible, and dependency-blocked work. Only requested ready items with satisfied dependencies may be selected.

Candidate verification failure may persist feedback and route a bounded **developer repair** attempt rather than terminating immediately. Attempt and cycle budgets are the minimum of policy and goal authority.

After post-merge verification, the controller commits `.agent-control/release-state.json` with a stable `Control-State-Id`, reloads authority, and reconciles the goal. It stops only when the requested objective is satisfied or when policy/authority prevents further progress.
