# Agent and reasoning model

## Why multiple roles

A single model call that plans, implements, tests and approves its own work is cheap and epistemically weak. The reference therefore separates responsibilities even when several roles use the same underlying model family.

Role separation is about **independent context and responsibility**, not theatrical job titles. Different phases receive different evidence, structured output schemas and authority.

## Canonical roles

### Discovery / chief architecture

Reads product-authored roadmap and release state, identifies one admissible work item, rejects work with unresolved dependencies and requests bounded additional context instead of guessing. Discovery does not edit product files.

### Task architect

Converts one accepted work item into a precise working set, states invariants and non-goals, identifies compatibility constraints, defines verification and classifies risk based on the actual change.

### Developer

Proposes the smallest implementation satisfying the plan, edits only the approved working set, maps changes to acceptance criteria and never claims that tests were executed by the model. The controller applies edits.

### Independent tester

Designs negative, boundary, regression and compatibility scenarios, adds executable tests within the independent-test namespace where allowed and assesses acceptance coverage separately from the implementation rationale.

### Reviewer

Inspects the exact candidate diff and evidence, reports correctness, architecture, security, compatibility, scope and testing findings and distinguishes blocking findings from maintainability suggestions.

## Full phase graph

```text
discovery
  -> task architecture
  -> independent test design
  -> chief plan gate
  -> implementation
  -> deterministic local verification
  -> independent tests
  -> deterministic independent verification
  -> review
  -> challenge review
  -> architecture acceptance
  -> chief acceptance
  -> publish candidate
  -> external CI
  -> merge authority gate
  -> merge
  -> post-merge verification
```

Low and medium risk may skip selected management/redundancy phases, but never deterministic verification, independent testing/review, candidate CI or post-merge evidence.

## Structured outputs

Every role returns a strict machine-readable result containing a verdict, summary, risk, bounded context requests, findings and phase-specific data such as task, plan, edits, test scenarios or acceptance evidence.

Unknown fields and missing required fields are protocol errors. Permissive parsing quietly turns model mistakes into controller assumptions.

A role may request more context, but only through a concrete bounded request such as an exact path, symbol search or documented lifecycle fact.

## Context retrieval

Each phase starts with a policy-approved authority subset and may request more through bounded channels:

- exact repository files;
- exact literal/symbol searches;
- documented lifecycle facts such as a specific pull request or recent merge evidence.

The controller performs retrieval. The model does not receive a general repository token or unrestricted shell merely because context is missing.

## Model selection

Policy may use one model for all roles or map roles individually. The reference does not require a public model name because model availability and capability change over time.

Selection should follow phase needs: strong long-context reasoning for discovery/architecture, reliable code transformation for development, independent adversarial reasoning for tester/reviewer and correctness over latency for high-risk acceptance.

A model upgrade changes runtime behavior and should therefore be explicit, reviewed and followed by a new activation epoch.

## Evidence taxonomy

### Authored authority

Roadmap item, architecture rule, acceptance criterion and forbidden direction. These define what is allowed and what success means.

### Model reasoning

Plan, risk assessment and review finding. Valuable analysis, but not proof that an external action occurred.

### Controller execution evidence

Exact command argv, exit code, log digest, observed test identities and candidate SHA. This proves deterministic work performed by the controller.

### External lifecycle evidence

Check identity, pull-request head SHA, merge SHA and post-merge check. This proves what happened in the external system.

Robust acceptance usually needs more than one evidence class.

## Test identity

Exit code zero is insufficient because a command can succeed while running zero tests. The example emits JUnit under `build/test-results/**` and starts with three real tests, making the baseline both human-readable and machine-verifiable.

## Risk and graph escalation

The goal defines the maximum authority the owner is willing to grant; actual work may still be classified more conservatively. If implementation reveals a critical path or higher risk, stronger gates are inserted and weaker candidate evidence is invalidated.

## Human decisions

Human intervention is reserved for authority changes or genuinely non-deterministic choices, such as high-risk implementation, critical paths, public contract changes outside explicit acceptance, destructive migration, controller/policy/credential changes, exhausted repair budgets or contradictory authoritative sources.

Everything deterministically resolvable should remain controller work.

## What a model never proves about itself

A model cannot establish that a command executed, tests passed, a check belongs to a SHA, a pull request merged, a state write succeeded or a credential/policy is valid. It may reason about those facts only after the controller supplies evidence from the authority that can know them.
