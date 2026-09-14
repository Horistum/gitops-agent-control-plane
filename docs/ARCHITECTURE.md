# Architecture

## Purpose

The reference demonstrates a control plane for autonomous engineering where a reasoning component can propose changes but cannot redefine its own authority or manufacture its own execution evidence.

## Four independent concerns

### Product authority

The product owns roadmap, architecture, forbidden directions and quality gates.

Authority describes **what is allowed and what success means**.

### Reasoning roles

Discovery, architecture, developer, tester and reviewer produce structured artifacts.

Reasoning may propose and assess. It is not accepted as proof that a command, test, merge or state write happened.

### Controller/executor

The controller owns path checks, state transitions, Git mutations, test execution, risk evaluation and evidence persistence.

This is where proposal becomes effect.

### Evidence

Evidence binds a claim to an observable identity: content digests, test identities, candidate SHA, merge SHA, event-chain hash and pending-effect request hash.

## Why the example roles are deterministic

The standalone implementation deliberately uses deterministic role outputs. This removes model variability while exposing the surrounding guarantees.

A production implementation may replace role producers with AI. It should not move policy enforcement, Git mutation, test execution or evidence authority into the model session.

## Lifecycle

```text
goal
  -> discovery
  -> plan
  -> proposal
  -> write-boundary decision
  -> candidate Git commit
  -> executable verification
  -> independent review
  -> risk/human-authority decision
  -> merge
  -> post-merge verification
  -> completion evidence
```

Negative outcomes are first-class terminal states, not exceptions to be hidden.

## Single source of truth

Product intent lives in `.agent-control/`.
Run state lives in `state.json`.
Event history lives in `events.jsonl`.

Human-readable summaries are projections of those facts, not competing databases.

## External-effect rule

Before an effect that cannot safely be repeated, persist:

1. effect kind;
2. exact request identity;
3. relevant candidate/base identity.

After the effect, persist the result and consume the pending intent.

The crash-recovery showcase demonstrates this with merge intent.
