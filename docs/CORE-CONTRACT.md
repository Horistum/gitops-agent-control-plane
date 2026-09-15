# Core autonomous control-plane contract

Contract: `autonomous-control-plane/v1`.

The core contract is deliberately separate from verification and runtime profiles. It defines **who may decide what**, **which state advances are authoritative**, and **what must remain true while autonomous work progresses**. It does not prescribe a particular model provider, probe protocol, Git hosting service, or container runtime.

## Authority classes

The reference separates five authority classes:

- **intent authority**: roadmap items and their dependency/acceptance structure;
- **state authority**: controller-recorded verified progress;
- **change authority**: paths and directions a proposal may or may not change;
- **verification authority**: product-authored gates and probe definitions;
- **context**: prose available to reasoning but not silently executed as policy.

`.agent-control/authority-model.json` is a product-owned **authority manifest**. It is not an operator toggle panel. Runtime loading verifies that machine-enforced artifacts are actually consumed and that product-owned authority files remain inside the protected authority path set. Only `release-state.json` may be controller-mutated, and only after verified effects.

## Goals and field semantics

Goal inputs distinguish executable authority from prose:

- `items` is `enforced_intent` and constrains work selection;
- `risk_ceiling`, `auto_merge_ceiling`, and `autonomy` are `enforced_authority`;
- `forbidden_paths` is an `enforced_constraint`;
- `objective`, `success_condition`, and `forbidden_directions` are `reasoning_context`.

`success_condition` is intentionally **not** an executable predicate in v1. The standalone engine computes `goal-evaluation.satisfied` from requested items versus controller-owned release state. Core library 1.1.0 separately provides `verification-evidence/v1` typed conditions; Flow consumes these through explicit `machine_conditions`. This extension never interprets prose or arbitrary expressions as executable authority.

## Reasoning-role protocols

`config/role-protocols.json` declares the bounded role surface for discovery, architect, developer, test-designer, tester, and reviewer. It is active runtime authority:

- `product_write_power: none` grants no proposal write envelope;
- `developer_allowed_paths` resolves to the developer path policy;
- `tester_allowed_paths` resolves to the diagnostic test-designer path policy;
- every reasoning role has `effect_power: none`.

The controller, not the role artifact, performs Git effects. Changing a role's declared write power changes proposal-gate behavior and is covered by direct regression tests.

## Reconciliation invariant

A conforming controller repeatedly:

1. validates authority and release-state semantics;
2. computes requested, completed, remaining, eligible, and dependency-blocked work;
3. selects only a dependency-ready requested item;
4. establishes the baseline and all preconditions required by its declared verification profile;
5. obtains bounded role proposals;
6. applies write, budget, risk, verification, and human-authority gates;
7. records verified Git effects and controller-owned progress;
8. retains the accepted evidence and regression obligations required by that verification profile;
9. reconciles the outer goal again.

The portable core does not require Python property probes. `property-probe/v6` requires case-level negative controls and probe promotion. Flow `counterfactual-regression/v1` requires executable test bindings, base/candidate counterfactuals and promotion of accepted test files; `external-cli/v1` evaluates typed process/artifact predicates outside the candidate. Capabilities must be declared and tested; these profiles are not interchangeable security guarantees.

A verification failure can feed a bounded repair attempt. A human `request_changes` decision is treated the same way: before a new candidate attempt, baseline diagnostics, regression probes, and the acceptance negative control are recomputed against the current `main` revision.

## Exact revision identity

A candidate is not merely a branch name. Candidate evidence records an exact Git SHA and a retained audit ref under `refs/tags/evidence/candidates/...` so rejected or superseded candidate objects remain reachable.

Human approval is bound to the reviewed candidate SHA. Immediately before an approval can create a merge effect, the controller re-resolves the candidate branch and requires its current tip to equal the reviewed SHA. The durable merge intent names exact base and candidate SHAs, and the runtime builds the merge from those commits rather than from a mutable branch name. Merge evidence checks both actual merge parents.

## Durable effects and phases

Durability has two layers.

First, before either Git side effect, the controller persists an intent with a stable effect identity:

- product merge: `Effect-Id` plus exact base/candidate SHAs;
- controller progress transition: `Control-State-Id` plus desired release-state digest.

A restart can observe an already-applied effect, prove it matches the durable intent, and avoid duplication.

Second, after an effect has been consumed, the durable phase identifies safe continuation points. `POSTMERGE_VERIFY` can replay exact-revision verification, and `RECONCILE` can continue from controller-owned release state without repeating a Git effect.

## What the core does not claim

The core contract does not make the standalone verifier a hostile-code sandbox. It does not make prose into policy, and it does not grant a reasoning role Git authority. The `property-probe/v6` verification profile and `standalone-local/v2` runtime profile supply concrete mechanisms for this repository; production adapters may replace them while preserving the core invariants above.
