# Portability

V7 has three compatibility surfaces: core contract `autonomous-control-plane/v1`, verification profile `property-probe/v6`, and runtime profile `standalone-local/v2`.

A compatible **core contract** preserves authority separation, goal semantics, role protocols, dependency-ready selection, bounded repair, human authority, durable effects, release-state transition, and reconciliation. Verification and **runtime profile** implementations may differ as long as these trust properties remain.

Candidate identity is an exact-revision property, including across durable human pauses. A human approval must be re-bound to the currently observed candidate object before effect execution, and the merge effect must consume the approved candidate revision itself rather than a mutable branch label. Merge evidence must prove the actual effect identities, for example by validating the merge parents against the expected base and candidate SHAs.

`config/contract-set.json` is a composition/version manifest, not a policy source. Policy and product authority come from their explicit authority surfaces; changing a profile identifier does not by itself grant new power.
