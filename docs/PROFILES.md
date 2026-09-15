# Contract and profile composition

The standalone reference is a composition of three independently versioned surfaces:

`autonomous-control-plane/v1` + `property-probe/v6` + `standalone-local/v2` = `gitops-agent-control-plane/v7`.

## Core contract

`autonomous-control-plane/v1` defines authority classes, goal semantics, reasoning-role boundaries, dependency-ready selection, bounded repair, human decisions, exact-revision effects, durable controller progress, recovery, and outer goal reconciliation.

Changing a verifier transport or Git provider does not require changing this core if those invariants remain true.

## Verification profile

`property-probe/v6` defines the standalone generated-case/invariant mechanism, negative controls, signed verifier receipts, and exact-revision verification evidence. The executable `raw-outcome-forgery` known limit belongs to this verification/runtime boundary, not to the generic autonomous core.

A different verifier may replace this profile if it preserves the verification authority expected by the core.

## Runtime profile

`standalone-local/v2` defines local Git/process adapters, deterministic role fixtures, process timeouts, exact-SHA merge mechanics, and local durable recovery. A GitHub, GitLab, Jenkins, Tekton, or Argo-backed implementation would be another runtime profile.

## `contract-set.json` is a compatibility manifest

`config/contract-set.json` is the machine-readable **implementation composition manifest**. It is intentionally exact for this reference implementation. It is not operator configuration and cannot grant authority.

The Python runtime rejects another contract set because it has not implemented another combination. A future implementation may support several known profile combinations through an explicit compatibility table, but accepting arbitrary version strings would not make the runtime more portable. It would merely make incompatibility quieter.

## `role-protocols.json` is active authority

Unlike the contract-set manifest, `config/role-protocols.json` participates directly in proposal authorization. `product_write_power` resolves to concrete policy path envelopes. Mutating that declaration changes proposal-gate behavior, and non-proposal roles are forbidden from acquiring product-write power.

`effect_power` is `none` for every reasoning role. Effects remain controller-owned.

## `authority-model.json` is a product authority manifest

`.agent-control/authority-model.json` declares classification, enforcement mode, and mutation owner for the product authority surface. Its entries are validated structurally plus against minimum core invariants rather than by comparing the entire document to one Python tuple table.

Runtime loading checks that machine-enforced artifacts are actually consumed and that product-owned authority files reside within protected authority paths. `release-state.json` is the only controller-mutated authority artifact in this reference.

These three files therefore have deliberately different semantics: compatibility manifest, active role authority, and product authority manifest. Treating all three as interchangeable “configuration” would erase precisely the boundaries v7 is meant to demonstrate.
