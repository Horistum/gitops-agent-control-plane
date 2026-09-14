# Portability

V7 has three compatibility surfaces: core contract `autonomous-control-plane/v1`, verification profile `property-probe/v6`, and runtime profile `standalone-local/v2`.

A compatible **core contract** preserves authority separation, goal semantics, role protocols, dependency-ready selection, bounded repair, human authority, durable effects, release-state transition, and reconciliation. Verification and **runtime profile** implementations may differ as long as these trust properties remain.
