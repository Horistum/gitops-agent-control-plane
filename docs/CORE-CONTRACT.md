# Authority and lifecycle contract

A model may propose work and explain it. The adapter authenticates product
intent and observations; the core computes bounded decisions; only the controller
performs effects. Public functions alone cannot authenticate a caller's booleans.

The complete shared graph reaches `independent_baseline` from `tester`, then
`independent_verify`. LOW/MEDIUM/HIGH and challenge paths all retain this order.
Risk review may return to `developer` or `verify`; an arbitrary saved return point
cannot jump to publication, merge or completion. Consumers that implement their
own profile-specific graph must establish equivalent preconditions explicitly.

## Operational profile

`agent_runtime` drives the complete shared graph for every item. Owner-held policy
and goal JSON snapshots define paths, risk and merge ceilings, dependencies, typed
acceptance, budgets, executable commands, providers and `machine_conditions`.
Product edits and model output cannot change these snapshots.

The owner account authenticates CLI actions. Approval binds exact base, candidate,
specification, risk, policy, runtime and run identity. Replan reconciles a published
PR and preserves frozen tests and risk. Cancel reconciles and verifies any observed
merge before stopping. Retrying does not reset the lifetime call budget. See
[OPERATIONS.md](OPERATIONS.md) for the command contract.

The remaining artifact names and `approve`/`reject`/`request_changes` examples
document the retained deterministic fixture contract. Its `release-state.json`,
human identity and property probes are not the operational run ledger. Both
profiles implement the same authority invariants.

## core-contract

Contract: the core contract (see the [generated table](../README.md#contracts)).

The core contract is deliberately separate from verification and runtime profiles. It defines **who may decide what**, **which state advances are authoritative**, and **what must remain true while autonomous work progresses**. It does not prescribe a particular model provider, probe protocol, Git hosting service, or container runtime.

### Authority classes

The reference separates five authority classes:

- **intent authority**: roadmap items and their dependency/acceptance structure;
- **state authority**: controller-recorded verified progress;
- **change authority**: paths and directions a proposal may or may not change;
- **verification authority**: product-authored gates and probe definitions;
- **context**: prose available to reasoning but not silently executed as policy.

`.agent-control/authority-model.json` is a product-owned **authority manifest**. It is not an operator toggle panel. Runtime loading verifies that machine-enforced artifacts are actually consumed and that product-owned authority files remain inside the protected authority path set. Only `release-state.json` may be controller-mutated, and only after verified effects.

### Goals and field semantics

Goal inputs distinguish executable authority from prose:

- `items` is `enforced_intent` and constrains work selection;
- `risk_ceiling`, `auto_merge_ceiling`, and `autonomy` are `enforced_authority`;
- `forbidden_paths` is an `enforced_constraint`;
- `objective`, `success_condition`, and `forbidden_directions` are `reasoning_context`.

`success_condition` is intentionally **not** an executable predicate in the fixture contract. That engine computes `goal-evaluation.satisfied` from requested items versus controller-owned release state. The core also provides typed conditions through `verification-evidence/v1`; the public operational runtime and Flow consume them through explicit `machine_conditions`. Prose is never interpreted as executable authority.

### Reasoning-role protocols

`config/role-protocols.json` declares the bounded role surface for discovery, architect, developer, test-designer, tester, and reviewer. It is active runtime authority:

- `product_write_power: none` grants no proposal write envelope;
- `developer_allowed_paths` resolves to the developer path policy;
- `tester_allowed_paths` resolves to the diagnostic test-designer path policy;
- every reasoning role has `effect_power: none`.

The controller, not the role artifact, performs Git effects. Changing a role's declared write power changes proposal-gate behavior and is covered by direct regression tests.

### Reconciliation invariant

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

The portable core does not require Python property probes. the verification profile (see the [generated table](../README.md#contracts)) requires case-level negative controls and probe promotion. Flow `counterfactual-regression/v1` requires executable test bindings, base/candidate counterfactuals and promotion of accepted test files; `external-cli/v1` evaluates typed process/artifact predicates outside the candidate. Capabilities must be declared and tested; these profiles are not interchangeable security guarantees.

A verification failure can feed a bounded repair attempt. A human `request_changes` decision is treated the same way: before a new candidate attempt, baseline diagnostics, regression probes, and the acceptance negative control are recomputed against the current `main` revision.

### Exact revision identity

A candidate is not merely a branch name. Candidate evidence records an exact Git SHA and a retained audit ref under `refs/tags/evidence/candidates/...` so rejected or superseded candidate objects remain reachable.

Human approval is bound to the reviewed candidate SHA. Immediately before an approval can create a merge effect, the controller re-resolves the candidate branch and requires its current tip to equal the reviewed SHA. The durable merge intent names exact base and candidate SHAs, and the runtime builds the merge from those commits rather than from a mutable branch name. Merge evidence checks both actual merge parents.

### Durable effects and phases

Durability has two layers.

First, before either Git side effect, the controller persists an intent with a stable effect identity:

- product merge: `Effect-Id` plus exact base/candidate SHAs;
- controller progress transition: `Control-State-Id` plus desired release-state digest.

A restart can observe an already-applied effect, prove it matches the durable intent, and avoid duplication.

Second, after an effect has been consumed, the durable phase identifies safe continuation points. `POSTMERGE_VERIFY` can replay exact-revision verification, and `RECONCILE` can continue from controller-owned release state without repeating a Git effect.

### What the core does not claim

The core contract does not make the standalone verifier a hostile-code sandbox. It does not make prose into policy, and it does not grant a reasoning role Git authority. The the verification profile (see the [generated table](../README.md#contracts)) verification profile and the runtime profile (see the [generated table](../README.md#contracts)) runtime profile supply concrete mechanisms for this repository; production adapters may replace them while preserving the core invariants above.

## human-authority

`NEEDS_DECISION` is a durable resumable authority boundary. It is not a pause-and-hope mechanism and it is not permission to merge whatever a mutable branch happens to contain later.

### What the human approves

A pending decision records:

- roadmap item and attempt;
- exact reviewed `candidate_sha`;
- candidate branch used as a mutable working reference;
- risk classification and reasons;
- allowed actions: `approve`, `reject`, `request_changes`.

The decision artifact also records the candidate SHA observed at decision time and whether that observation still matches the reviewed SHA.

### Approval is revision-bound

Immediately before `approve` can create a merge effect, the controller re-resolves `candidate_branch`. The current branch tip must equal all of:

1. the candidate SHA stored in durable state;
2. the SHA persisted in the pending human decision;
3. the reviewed candidate evidence SHA.

If the branch moved, disappeared, or resolves to another commit, approval fails closed with `BLOCKED_POLICY`. The `human-approve-after-tamper` conformance scenario moves the branch after review, adds a backdoor commit, and proves that the subsequent approval does not merge it.

### Merge semantics

The durable merge intent contains exact `base_sha` and `candidate_sha`. The runtime creates the merge from those commit objects, not from a branch name. Before advancing `main`, the local Git adapter requires current `main` to still equal the intended base and updates the ref with compare-and-swap semantics.

After creation, merge evidence verifies both parents:

- first parent equals the intended base SHA;
- second parent equals the approved candidate SHA.

The merge is therefore revision-bound at authorization, execution, and evidence consumption.

### Actions

#### `approve`

Continue with the exact-SHA merge, post-merge verification, controller release-state transition, and goal reconciliation. A stale approval is rejected rather than reinterpreted.

#### `reject`

Record the human decision, block the work item, delete the mutable candidate branch, and leave the retained candidate audit ref intact.

#### `request_changes`

Convert the paused attempt into bounded repair feedback, discard the mutable candidate branch, and begin the next attempt only after recomputing baseline diagnostics, completed-item regression probes, and the acceptance negative control on the current `main` revision. Previous preconditions are never reused for a new base revision.

### Candidate retention

Every committed candidate receives a controller-created audit ref under `refs/tags/evidence/candidates/<run>/<item>/attempt-XX`. Candidate evidence records that ref. Deleting a transient candidate branch therefore does not make the reviewed commit unreachable or dependent on Git reflog retention.

### Production identity

The deterministic reference records `conformance-human`. A production adapter must bind the decision to an authenticated human identity and should preserve whatever organizational authorization evidence is required. Identity authentication is additional to, not a substitute for, exact revision binding.

## policy

V7 policy provides controller upper bounds for write scopes, risk, change budgets, test timeout, autonomous cycles, and attempts per item. Goal authority may narrow but not exceed those bounds. Product authority is classified into intent, state, change, verification, and context. Completed-item acceptance probes carry forward as later regression requirements.

## reconciliation

The outer reconciliation loop is what turns a bounded patch executor into an autonomous control plane. `COMPLETED` for one candidate is not automatically completion of the requested goal.

### Goal projection

At every reconciliation point the controller computes a machine projection containing:

- requested roadmap items;
- controller-recorded completed items;
- remaining items;
- currently eligible dependency-ready items;
- remaining items blocked by unsatisfied dependencies;
- `satisfied`, derived from requested items versus release-state completion.

The human-readable `goal.success_condition` is reasoning context. It is not parsed as an executable predicate in the core contract (see the [generated table](../README.md#contracts)). `goal-evaluation.satisfied` is the machine completion projection.

### Work selection

Only an item that is all of the following may be selected:

1. explicitly requested by goal intent;
2. present in validated roadmap authority;
3. marked `ready`;
4. not already controller-recorded complete;
5. dependency-ready according to validated release state.

If requested work remains but no authorized dependency-ready item exists, the controller fails closed rather than inventing work outside roadmap authority.

### Preconditions per cycle

Before the first proposal attempt for an item, the controller runs:

- protected diagnostic baseline tests;
- baseline verification probes plus all acceptance probes promoted from previously completed items;
- a case-level negative control proving the selected item's new acceptance behavior is not already satisfied by the current baseline.

These checks are bound to the current Git base.

### Repair feedback

Candidate verification failure can persist blocking findings and route a bounded developer repair attempt instead of immediately terminating. Attempt and cycle budgets are the minimum of product policy and goal authority.

A repair attempt is not permission to reuse stale verification context. Human `request_changes` therefore reruns the same baseline/regression/negative-control preconditions against the current `main` revision before the next proposal. `retry-preconditions-<item>-attempt-XX.json` records the base SHA and each precondition result.

### Candidate history

Transient candidate branches may be removed during repair, rejection, or cleanup, but each committed candidate is retained by an evidence tag under `refs/tags/evidence/candidates/...`. The exact object named by candidate evidence therefore remains reachable for later audit.

### Verified progress

After exact post-merge verification, release-state advancement is a second durable controller effect. The controller first persists a `control-state` intent containing:

- item identity;
- exact verified merge SHA;
- desired release-state content;
- desired-state digest;
- stable `Control-State-Id`.

Only then is `.agent-control/release-state.json` committed. The consume step rereads the observed state and requires its digest to equal the durable intent before progress is accepted.

### Recovery boundaries

If the process terminates before effect receipt consumption, a fresh process can locate the Git effect by stable trailer identity, verify it, avoid duplication, and continue.

Durability also covers crashes after an effect has been consumed. `POSTMERGE_VERIFY` is safely replayable against the already-recorded exact merge SHA. `RECONCILE` is safely continuable from controller-owned release state with no pending side effect. `phase-recovery.json` records the phase and replay/continue action.

The controller stops only when the requested item projection is satisfied or when policy, authority, or bounded autonomy prevents further progress.
