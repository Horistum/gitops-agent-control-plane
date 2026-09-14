# Release and versioning policy

Current repository contract: `gitops-agent-control-plane/v7`.

Composition: core `autonomous-control-plane/v1`, verification `property-probe/v6`, runtime `standalone-local/v2`.

Public tags use `vMAJOR.MINOR.PATCH`; intended first public release remains `v0.1.0` after clean-room publication gates. V7 is breaking because it adds multi-item reconciliation, repair, human resume, release-state transitions, role protocols, and adapter surfaces. A profile change no longer automatically changes the core contract.
