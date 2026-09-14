# Contract and profile composition

`autonomous-control-plane/v1` + `property-probe/v6` + `standalone-local/v2` = `gitops-agent-control-plane/v7`.

The core defines goals, authority, roles, repair/replanning, human decisions, durable effects, release-state transitions, and goal reconciliation. The verification profile defines the standalone property-probe evidence mechanism. The runtime profile provides local Git/process execution and deterministic role fixtures. Alternative profiles may replace either without changing the core contract.
