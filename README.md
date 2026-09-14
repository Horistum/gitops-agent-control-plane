# GitOps Agent Control Plane Reference

A **standalone executable reference** for bounded autonomous software delivery through Git.

This repository is intentionally not a product brochure and is not tied to any private controller, model provider, or internal project. Its purpose is to make the important mechanics visible and testable:

- who is allowed to decide what;
- how an autonomous system is prevented from rewriting its own rules;
- how planning, implementation, testing, review, risk, merge and recovery remain separate concerns;
- how evidence is bound to exact Git identities;
- how failed tests, forbidden paths and critical changes stop progress instead of being explained away;
- how a crashed controller can resume a pending effect without duplicating it.

The reference runs locally with **Bash, Git and Python 3.11+**. No account, token, model, container engine or external service is required.

## Try the idea in one command

```bash
./scripts/agentctl demo happy-path
```

The runtime copies the example product into an isolated workspace, initializes a real local Git repository, runs the green baseline, creates a bounded plan, proposes and applies a candidate, runs executable acceptance tests, records an independent review, creates a real candidate commit, performs a real local merge commit, verifies the merged result and writes audit evidence.

Typical summary:

```text
status: COMPLETED
baseline tests: 3
candidate tests: 5
candidate SHA: <real git SHA>
merge SHA: <different real git SHA>
post-merge tests: 5
```

Evidence is written under:

```text
.demo/runs/<run-id>/evidence/
```

## The interesting part is not the happy path

Run the full behavioral matrix:

```bash
./scripts/agentctl demo all
```

or:

```bash
./scripts/agentctl conformance
```

It exercises five scenarios:

| Scenario | What it proves | Expected result |
|---|---|---|
| `happy-path` | bounded goal → plan → candidate → tests → review → merge → post-merge evidence | `COMPLETED` |
| `forbidden-path` | an implementation cannot rewrite product authority | `BLOCKED_POLICY` |
| `test-failure` | a plausible implementation with failing executable evidence cannot merge | `FAILED_VERIFICATION` |
| `human-gate` | a critical path raises risk and stops for human authority | `NEEDS_DECISION` |
| `crash-recovery` | a persisted pending effect can be recovered without duplicating the effect | `COMPLETED` |

That is the point of the reference. Autonomous delivery is not impressive because a model can write a patch. It becomes interesting when the surrounding system can reliably decide **what the model may change, what counts as proof, when automation must stop, and how execution can be recovered**.

## What the runtime actually produces

A successful run includes artifacts such as:

```text
goal.json
policy.json
authority-snapshot.json
role-discovery.json
plan.json
role-architect.json
proposal.json
candidate.patch
policy-decision.json
candidate-evidence.json
test-baseline.json
test-candidate.json
role-tester.json
review.json
risk-decision.json
merge-evidence.json
test-postmerge.json
postmerge-evidence.json
state.json
events.jsonl
run-summary.json
```

The crash-recovery scenario adds durable effect intent and recovery evidence. The human-gate scenario adds an unresolved human decision artifact. The forbidden-path scenario deliberately creates no candidate commit.

## Architecture in one picture

```text
Product-authored authority
        │
        ▼
      Goal
        │
        ▼
   Discovery role
        │
        ▼
 Bounded architecture plan
        │
        ▼
 Developer proposal ───────► Policy/write-boundary gate
        │                          │
        │                          └── reject if authority/out-of-scope
        ▼
 Exact candidate Git commit
        │
        ▼
 Executable tests + independent review
        │
        ▼
 Risk / critical-path decision
       / \
      /   \
auto-safe  human authority required
    │
    ▼
 Exact merge Git commit
    │
    ▼
 Post-merge verification
    │
    ▼
 Durable evidence + hash-linked event history
```

The reference separates **authority**, **reasoning**, **execution** and **evidence**. A role may claim that a change is correct. Only executable tests and Git/evidence identities can prove what actually happened.

## Repository map

```text
reference_runtime/     executable reference state machine
schemas/               portable JSON Schema contracts
config/                standalone reference policy
examples/
  minimal-product/     deliberately small product with authored authority
  goal.example.json    owner goal
scripts/
  agentctl             single operator entry point
  bootstrap-linux.sh   Linux prerequisite helper
  diagnose-linux.sh    read-only diagnostics
  cleanup-linux.sh     remove only local demo artifacts
tests/                 conformance/runtime tests
docs/
  SHOWCASE.md          walk-through of the five scenarios
  ARCHITECTURE.md      trust boundaries and control-plane model
  STATE-MACHINE.md     durable phases and terminal states
  EVIDENCE.md          evidence provenance and event chaining
  MODEL.md             role separation and reasoning boundaries
  POLICY.md            authority and risk model
  PORTABILITY.md       contract for alternative implementations
  SECURITY.md          threat model
  VERIFICATION.md      what each test layer really proves
  ADOPTION.md          how to adapt the reference to a real product
  LINUX.md             Linux usage
```

## Validate the repository

```bash
./scripts/agentctl validate
```

This runs repository checks and the complete conformance matrix.

CI runs the same validation on pull requests and on `main`.

## Product authority is not implementation scope

The example product contains:

```text
examples/minimal-product/.agent-control/
```

These files define the roadmap, architecture, forbidden directions and quality gates. The reference runtime can read them, but its implementation write envelope excludes them.

The `forbidden-path` scenario attempts to change an authority file on purpose and demonstrates that the controller blocks the proposal **before a candidate side effect exists**.

## Portable contracts

Formal JSON Schema contracts live under `schemas/` for:

- goal;
- policy;
- bounded plan;
- durable state;
- terminal evidence.

The reference runtime is one implementation of those ideas. Another implementation is useful only if it preserves the same authority/evidence properties, not merely because it can open a pull request.

## Linux

Check the small standalone prerequisite set:

```bash
./scripts/agentctl bootstrap check
```

Automatic provisioning is available for Debian/Ubuntu and Fedora/RHEL-family systems:

```bash
./scripts/agentctl bootstrap prepare
```

The showcase deliberately does **not** require GitHub CLI, Podman, a model CLI or systemd services.

## What this repository does not claim

It does not claim that deterministic demo roles are equivalent to a production AI system. They are deliberately predictable so the control-plane mechanics can be inspected without an external black box.

The reference demonstrates the difficult surrounding properties: authority, isolation, exact identity, executable evidence, risk escalation, human boundaries, state recovery and conformance.

A real AI implementation can replace the deterministic role producers later. It should not be allowed to replace those guarantees.
