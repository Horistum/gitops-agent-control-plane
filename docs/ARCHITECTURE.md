# Architecture and authority model

## 1. The three-plane model

A safe FlowAI-Control deployment has three repositories/authorities with different jobs.

### Runtime source authority

`Horistum/FlowAi-control` owns executable controller code, trusted role instructions, parsers,
policy validation, evidence logic and release manifests. This reference pins an exact reviewed
commit in `COMPATIBILITY.json`.

A tenant does not copy those files into its control repository. `scripts/install_runtime.py`
retrieves the pinned commit, verifies the exact Git tree against `RELEASE-MANIFEST.json`, copies the
manifested runtime into a versioned local directory and executes that immutable installation.

### Tenant control/state authority

The adopter's private copy of this repository is configured as `policy.control_repo`.

It provides:

- the owner command issue;
- the Flow Loop Goal Issue Form;
- ordinary reviewed documentation/configuration scaffolding on `main`;
- the controller-owned `loop-state` branch.

`loop-state` is not a human-edited configuration branch. It is the remote-first execution journal.
FlowAI-Control writes `state.json`, hash-linked `events/`, immutable `runs/`, task `reports/` and a
human-readable `DASHBOARD.md` there. The controller identity is single-writer and pushes are
non-force.

The command issue is a control surface and projection. It is not the state database.

### Product authority

`policy.product_repo` is the repository FlowAI-Control may modify.

The product owns:

- application source;
- roadmap and acceptance semantics;
- architecture/quality authority documents;
- trusted CI;
- server-side `main` governance.

The control policy limits which paths may be modified. The engine also has hard-denied paths that a
normal product task cannot authorize.

## 2. Authority precedence

The useful mental model is:

```text
owner GoalEnvelope + static policy
            |
            v
authored product authority documents
            |
            v
controller deterministic gates
            |
            v
model proposals
```

Models propose. They do not grant authority. Repository text is untrusted data when supplied to a
model. A model cannot make a forbidden change valid by describing it persuasively.

## 3. End-to-end execution

A normal v0.3.0 run is:

```text
owner creates immutable Goal Issue
        |
        v
GoalEnvelope parsed and bounded by policy
        |
        v
discovery selects one admissible roadmap item
        |
        v
exact product main SHA becomes baseline
        |
        v
task architecture / risk classification
        |
        +------ LOW --------> minimal adaptive graph
        |
        +------ MEDIUM -----> independent test design + stronger acceptance
        |
        +------ HIGH -------> full graph + owner decision boundary
        |
        v
developer proposal -> controller applies bounded edits
        |
        v
rootless networkless local test container
        |
        v
independent tester / reviewer / optional challenge
        |
        v
candidate PR -> exact trusted GitHub checks
        |
        v
owner approval if policy/risk requires it
        |
        v
merge -> checks on exact merge SHA
        |
        v
durable completion evidence -> next goal item
```

The exact graph is selected by controller code. Documentation must not pretend every risk level uses
the same roles or that a model can skip a deterministic gate.

## 4. State and effect identity

Every external effect is bound to durable identity before execution. Current FlowAI-Control receipts
bind controller version, policy fingerprint, activation epoch, run id, phase, task, base/head SHAs,
specification hash, effect kind and request hash.

That is why stale model output or old CI cannot silently satisfy a new activation.

A fresh activation is an explicit owner comment:

```text
/loop activate <current-policy-fingerprint>
```

The immutable GitHub comment id becomes the execution epoch identity.

## 5. Initial state

A new control repo normally has no `loop-state` branch. FlowAI-Control can load this as an initial
paused state. The first accepted owner command persists the first state/event commit to
`loop-state`.

Do not manually pre-create fake `state.json`. That bypasses the controller's event-chain creation
rather than helping it.

## 6. Why the source/control split matters

FlowAI-Control 0.3.0 runtime code can already use separate `product_repo` and `control_repo`.
However, the upstream 0.3.0 upgrade helper still validates its source commit against the configured
`control_repo`, reflecting the original Horistum pilot where source and control were one repository.

This reference therefore installs the pinned runtime directly instead of invoking that tenant-
incompatible upgrade helper. See `LIMITATIONS.md`.
