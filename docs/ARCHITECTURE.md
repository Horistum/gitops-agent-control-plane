# Architecture

## 1. Goal

The control plane turns a high-level engineering goal into a bounded sequence of verifiable Git operations without giving a model unrestricted repository authority.

The key decision is separation of **intent**, **execution state**, **runtime mechanics** and **verification**. If one component owns all four, autonomy is easy to implement and difficult to trust.

## 2. Components and authorities

### Product repository

The product repository is the source of authored engineering truth. It contains source, tests, architecture constraints, roadmap/work items, release state, quality gates, forbidden directions and CI workflows.

Authority documents are outside the ordinary agent write envelope. The agent may read what success means, but cannot redefine success as part of the same product change.

### Control repository

The control repository is the remote coordination surface. It contains a long-lived control-center issue, owner goal requests, a dedicated state branch, append-only event history, immutable external-effect receipts and generated reports.

### Runtime adapter

The runtime adapter is replaceable. Its responsibilities are contractual:

1. load and validate policy;
2. read product authority at an exact base SHA;
3. execute role phases with bounded context;
4. apply only controller-approved edits;
5. run deterministic verification outside the model session;
6. create and inspect pull requests/checks;
7. persist state before and after external effects;
8. enforce merge and post-merge gates;
9. fail closed when identity, authority or evidence is ambiguous.

The backend pinned by `COMPATIBILITY.json` is one implementation of this interface. The portable product example does not depend on its branding or repository layout.

### External verifiers

CI is a separate authority. A check is trusted only when policy binds both its context/name and the application identity that produced it. The controller also verifies that the check belongs to the exact candidate or merge SHA.

## 3. Data flow

```text
Owner goal
   |
   v
Goal envelope / authority ceiling
   |
   v
Discovery from product-authored roadmap
   |
   v
Architecture plan -> implementation -> independent tests/reviews
   |
   v
Controller-executed deterministic local verification
   |
   v
Candidate commit + PR
   |
   v
Trusted CI on exact candidate SHA
   |
   v
Risk / critical-path / merge-authority decision
   |
   v
Merge
   |
   v
Trusted post-merge CI on exact merge SHA
   |
   v
Durable completion evidence
```

The model never turns its own statement such as “tests pass” into a green gate. It can explain why a change should work; a deterministic executor and external CI must prove what actually happened.

## 4. State model

The authoritative state is remote-first and single-writer. At minimum it records controller identity, monotonically increasing sequence, active goal/task, current phase, exact base/candidate/merge SHAs, risk and critical paths, pending external effect identity, model/test/review receipts, completed items, pause/drain state, activation epoch and hash-linked event tip.

A human-facing dashboard or issue body is a projection of this state, not a second database.

## 5. External-effect protocol

Every expensive, non-deterministic or externally visible operation follows a durable intent protocol:

1. calculate the exact request identity;
2. persist operation intent;
3. bind effect kind and request hash;
4. perform the external call;
5. write an immutable receipt carrying runtime, policy, epoch, task, phase and SHA provenance;
6. persist the state transition that consumes the receipt.

After a crash, the controller first looks for a matching receipt. Evidence from another policy, runtime activation or Git SHA is rejected.

## 6. Single-writer property

The state branch uses non-force writes. A second writer therefore cannot silently overwrite a changed remote tip. Controller identity is also stored in state, so a planned host transfer is explicit.

This is not distributed consensus. Two hosts with the same writer identity must not run in parallel.

## 7. Write boundaries

There are three nested controls:

- runtime hard-deny paths;
- policy `allowed_paths` defining the tenant envelope;
- phase-specific working set selected by architecture planning.

A developer proposal outside any boundary fails closed.

## 8. Adaptive role graph

| Effective risk | Required shape |
|---|---|
| LOW | plan, implementation, deterministic verification, independent tests, review, CI, merge, post-merge |
| MEDIUM | LOW plus independent test design and architecture acceptance |
| HIGH / critical path | MEDIUM plus chief architecture gates and explicit owner decision where required |

Risk escalation invalidates evidence that was sufficient only for the weaker graph.

## 9. Trust boundaries

The model receives repository text as **data**, not executable instructions. Model sessions do not inherit GitHub credentials, are not the component applying patches, and do not execute arbitrary shell commands. The controller owns mutations and deterministic execution.

## 10. Portability boundary

The portable contract is defined by behavior, not one process name or command syntax. Another runtime is compatible when it provides bounded goals, explicit policy, single-writer durable state, structured role outputs, exact-SHA evidence, deterministic tests, trusted CI identities and fail-closed merge semantics.

Backend-specific translation belongs in adapter scripts, not in product semantics or core architecture documentation.
