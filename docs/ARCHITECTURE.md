# Architecture

The architectural center is **goal reconciliation**, not one patch lifecycle.

Contract layers: core `autonomous-control-plane/v1`, verification profile `property-probe/v6`, runtime profile `standalone-local/v2`.

Product authority is classified into intent, state, change, verification, and context. Each reasoning **role protocol** has explicit inputs/outputs and no Git-effect power.

Lifecycle: goal reconciliation → dependency-ready selection → discovery → bounded plan → proposals → policy/budget/risk gates → candidate → verification → computed review → feedback/repair or human authority → durable merge → post-merge verification → controller release-state effect → goal reconciliation.

The runtime uses real verification-execution and Git-effect adapter surfaces. Production hostile-code verification still requires stronger isolation than the local fixture profile.
