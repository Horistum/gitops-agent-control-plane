# Contract and profile composition

`autonomous-control-plane/v1` + `property-probe/v6` + `standalone-local/v2` = `gitops-agent-control-plane/v7`.

The core defines goals, authority, roles, repair/replanning, human decisions, durable effects, release-state transitions, and goal reconciliation. The verification profile defines the standalone property-probe evidence mechanism. The runtime profile provides local Git/process execution and deterministic role fixtures. Alternative profiles may replace either without changing the core contract.

`config/contract-set.json` is the machine-readable **composition manifest** for those versioned surfaces. It is intentionally not an authorization document and cannot grant write/effect power. Role write authority is declared separately by `config/role-protocols.json` and resolved to concrete policy write envelopes by the controller. Product artifact ownership and controller mutation rights are declared by `.agent-control/authority-model.json` and are consumed by the proposal and controller-state gates.
