# Portability contract

## What is portable

The following concepts are independent of a particular controller implementation:

- product-authored roadmap and acceptance criteria;
- separate control and product repositories;
- explicit goal authority ceilings;
- role-separated planning, implementation, testing and review;
- phase-specific context budgets;
- bounded write envelopes and critical paths;
- deterministic tests outside model sessions;
- exact-SHA CI and merge evidence;
- single-writer durable state;
- external-effect intent/receipt identity;
- adaptive risk gates;
- owner decision boundaries;
- post-merge verification.

These concepts are the actual subject of the reference repository.

## Runtime adapter responsibilities

A backend adapter must provide mappings for four things:

1. **Policy** – portable authority choices into runtime configuration.
2. **Goal transport** – portable goal JSON into accepted intake protocol.
3. **Operator commands** – stable owner verbs into backend-specific control messages.
4. **Installation/verification** – pin and prove exact runtime bytes before activation.

The current implementation lives in `scripts/render_policy.py`, `scripts/submit_goal.py`, `scripts/control.py` and `scripts/install_runtime.py`.

## Replacing the backend

To adopt another orchestration engine without changing the example product, keep `.agent-control/*` semantics, preserve the goal JSON or provide a compatible translator, preserve CI producer identity plus exact candidate/merge SHA evidence, preserve the no-model-direct-mutation boundary and equivalent state/effect durability, then update `COMPATIBILITY.json` and adapter contract tests.

A backend is not considered compatible merely because it can open a pull request. The evidence and authority model are part of the interface.

## Current concrete adapter

`COMPATIBILITY.json` intentionally contains the only top-level binding to concrete runtime source. That binding is pinned by commit rather than following a moving branch. The rest of the repository uses generic terminology so the reference remains useful when the backend changes.
