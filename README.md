# GitOps Agent Control Plane Reference

A **standalone executable reference for bounded autonomous software delivery through Git**.

**Initiated and maintained by the Horistum project.**

The reusable implementation lives in `control_plane_core` and is consumed by
`Horistum/FlowAi-control` as exact, versioned source bytes. See
[shared core and runtime profiles](docs/SHARED-CORE.md) for the integration contract,
validation boundary and synchronization command.

Core library 1.2.0 also provides `verification-evidence/v1`: executable acceptance
bindings, counterfactual/regression semantics and typed external CLI predicates.
The separately runnable `agentctl verify-cli --trusted-fixture` extension is
described in [profiles](docs/PROFILES.md); Flow uses the same predicates in its
rootless production adapter.

Core 1.2.0 also shares staged acceptance, repair routing, recovery limits, attempt
identity and bounded phase-private context decisions. The public reference engine
executes typed behavior, compatibility, documentation and delivery criteria; its
local profile rejects hosted CI criteria before execution. See [shared execution](docs/SHARED-EXECUTION.md).

The current repository contract is `gitops-agent-control-plane/v7`, composed from:

- **core contract:** `autonomous-control-plane/v1`
- **verification profile:** `property-probe/v6`
- **runtime profile:** `standalone-local/v2`

The split is intentional. Autonomy, verification, and runtime/provider mechanics can evolve without pretending they are the same contract.

## The central idea

AI or another reasoning provider is not given unrestricted execution authority. It operates inside a control plane:

```text
product authority
      ↓
goal
      ↓
discovery / selection
      ↓
bounded plan
      ↓
developer + test-design proposals
      ↓
policy / risk / budgets
      ↓
candidate
      ↓
independent verification
      ↓
review
      ↓
human authority when required
      ↓
durable Git effect
      ↓
post-effect verification
      ↓
release-state transition
      ↓
goal reconciliation
      ├─ objective projection satisfied → stop
      └─ work remains → select next dependency-ready item
```

Authority, effects, risk, verification, durable state, and evidence remain outside reasoning-role control.

## One-command autonomous showcase

```bash
./scripts/agentctl loop
```

The default `autonomous-two-item` scenario delivers two dependent roadmap items in one control-plane run. The controller selects `EXAMPLE-001`, verifies and merges it, commits a controller-owned release-state transition, re-evaluates the goal, unlocks `EXAMPLE-002`, preserves the first item's acceptance probes as regressions, and stops only when the requested item projection is satisfied.

Other important scenarios include:

```bash
./scripts/agentctl demo repair-loop
./scripts/agentctl demo human-approve-resume
./scripts/agentctl demo human-approve-after-tamper
./scripts/agentctl demo dependency-blocked
./scripts/agentctl conformance
```

`repair-loop` demonstrates verification feedback returning to a bounded developer repair attempt rather than making every failed candidate terminal.

`human-approve-resume` demonstrates `NEEDS_DECISION` as a durable resumable authority boundary. A fresh process records the human decision and continues the same run.

`human-approve-after-tamper` moves the candidate branch after review and proves that approval is bound to the exact reviewed SHA, not to a mutable branch name.

`dependency-blocked` proves the controller will not invent work outside declared dependency authority merely to make progress.

## Authority is explicit

Product authority is classified into:

- **intent authority:** roadmap and desired work;
- **state authority:** controller-recorded release progress;
- **change authority:** structured forbidden/write boundaries;
- **verification authority:** quality gates and product invariants;
- **context:** prose that reasoning may use but the controller does not silently execute.

`examples/minimal-product/.agent-control/authority-model.json` makes this machine-visible. It is an authority manifest, not a bag of arbitrary feature flags.

Goal fields are also classified. `items`, risk ceilings, auto-merge ceilings, forbidden paths, and autonomy budgets are machine enforced. Narrative objective, `success_condition`, and forbidden-direction prose are reasoning context. Machine completion is the separate `goal-evaluation.satisfied` projection computed from controller-owned release state. The runtime does not claim to interpret success prose as executable policy.

## Reasoning roles are protocols

Discovery, architect, developer, test-designer, tester, and reviewer have explicit input/output contracts in `config/role-protocols.json`.

Role write power is active runtime authority: proposal gates resolve each proposal-producing role's `product_write_power` to a concrete policy path envelope. No reasoning role has direct Git-effect authority.

The standalone implementation uses deterministic fixture role providers so controller behavior is reproducible. A production system may replace those producers with AI while preserving the same authority/effect/evidence boundaries.

## Exact candidate identity

Candidate evidence records an immutable Git SHA plus a retained audit ref under `refs/tags/evidence/candidates/...`. Transient candidate branches may be deleted during repair or rejection without making the reviewed commit unreachable.

Human approval re-resolves the candidate branch immediately before authorization. If its tip no longer equals the reviewed SHA, approval fails closed. The durable merge effect names exact base/candidate SHAs, builds the merge from those commits, advances `main` with compare-and-swap semantics, and verifies both actual merge parents before consuming the effect.

## Verification profile

The v7 core reuses the hardened `property-probe/v6` verification profile:

- product-authored generic invariant DSL;
- bounded DSL depth and static arg/kwarg/type reference validation;
- case-level negative control;
- exact candidate/merge binding;
- HMAC-authenticated verifier-parent receipts;
- diagnostic JUnit kept non-authoritative;
- executable negative scenarios;
- executable `raw-outcome-forgery` **KNOWN-LIMIT**.

Verification is a profile of the control plane, not the definition of the control plane.

## Human authority and repair

A risk or auto-merge boundary creates durable `NEEDS_DECISION` state with allowed actions:

- `approve`
- `reject`
- `request_changes`

Approval is valid only for the exact reviewed revision. Rejection terminates without merge. `request_changes` creates repair feedback and, before the next proposal attempt, reruns baseline diagnostics, completed-item regression probes, and the acceptance negative control against the current `main` revision.

## Git as the control/effect ledger

In this reference, “GitOps” means that desired product authority, candidate identities, merge effects, controller-owned release-state transitions, retained audit refs, and recovery identities are represented through versioned Git state.

Provider-specific GitHub/GitLab/Argo/Jenkins behavior is a runtime adapter concern, not part of the core contract.

## Trust boundary

The local fixture runtime is not a hostile-code security sandbox. `raw-outcome-forgery` deliberately reproduces the acknowledged same-process observation weakness. Production arbitrary-code verification requires a stronger container/VM/remote verifier and independently protected result channel.

The CLI repeats this warning in `agentctl help` because an operator should not have to remember which paragraph of README contains the most important runtime limitation.

## Validate

```bash
./scripts/agentctl validate
```

Validation covers schemas/static contracts, direct code-path unit tests, the full security regression matrix, exact-revision human approval, and autonomous-control-loop scenarios on Python 3.11, 3.12 and 3.13.

## Origin, license and branding

This reference architecture was originally developed and published from the **Horistum GitHub organization**.

Source, documentation, schemas, and examples are Apache-2.0 licensed. See `LICENSE`, `NOTICE`, and `TRADEMARKS.md`.
