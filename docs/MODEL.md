# Reasoning-role model

The reference separates roles because "the same intelligence checked its own homework" is a weak assurance model, even when the intelligence is impressive.

## Roles

### Discovery

Selects an authorized ready work item from product-authored roadmap data.

### Architect

Defines working set, acceptance mapping, verification and non-goals.

### Developer

Produces a proposal. The developer does not directly write authority or execute merge operations.

### Tester

Evaluates executable acceptance/regression evidence separately from developer reasoning.

### Reviewer

Evaluates scope, authority preservation, executable evidence and blocking findings.

## Deterministic implementation

In this repository these roles are deterministic reference producers. That makes the showcase:

- offline;
- repeatable;
- auditable;
- free from provider/model branding.

The point is to demonstrate the control-plane contract.

A production AI integration may replace role producers, but the controller must still independently enforce policy and execute tests/effects.

## What reasoning never proves

A reasoning artifact cannot prove:

- that a test process actually ran;
- which Git SHA was tested;
- that a merge happened;
- that state was persisted;
- that a pending effect was recovered;
- that an authority boundary was respected.

Those claims require evidence from the component that can observe the fact.
