# Core autonomous control-plane contract

Contract: `autonomous-control-plane/v1`.

The core contract is deliberately separate from verification and runtime profiles.

## Invariants

A conforming implementation must preserve: product authority outside implementation scope; explicit goal intent and authority; typed reasoning-role protocols with no effect power; dependency-ready work selection; bounded planning/proposals; verification feedback and bounded repair; independent risk/human authority; durable effect identity; controller-owned release-state progress; completed-item regression protection; and outer goal reconciliation after every verified effect.

**Durable effect identity applies to both product merges and controller-owned state transitions.** Before either Git side effect, the controller persists an intent carrying a stable effect identity. A process restart must be able to observe an already-applied effect, avoid duplication, consume its evidence, and continue reconciliation.

## Goal field semantics

`reasoning_context` is visible to reasoning but not silently executed. `enforced_intent` constrains selection. `enforced_authority` bounds risk/merge/autonomy. `enforced_constraint` is directly evaluated. `verified_projection` is prose whose completion is computed from machine state/evidence.

The core contract does not prescribe HMAC, JUnit, containers, GitHub, or a specific AI provider.
