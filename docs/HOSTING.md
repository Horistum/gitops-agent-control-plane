# Deployment scope and supported storage

The project provides a reusable governance core and an owner-operated runtime
for bounded software delivery through Git. Its local persistence is an intentional,
supported architecture. PostgreSQL is not a project requirement or a selected
future backend. No database migration is needed to use or complete this runtime.

An earlier version of this document turned a hypothetical shared-hosting review
into a required SaaS migration plan. That interpretation was incorrect. A shared
multi-tenant service would be a separate deployment decision, not an implied
prerequisite or a measure of completeness for this project.

## Supported state and concurrency model

| Component | Current responsibility |
|---|---|
| `state.json` | Durable run state and the owner-authorized policy/goal snapshot |
| Effect intents and receipts | Recovery, request/result identity and explicit uncertain outcomes |
| Per-run `flock` | Admit one writer for a run at a time across local processes |
| Atomic replace and fsync | Durable local JSON updates |
| Run-owned `product.git` | Exact source, candidate and merge objects |
| `RunService` and `tick` | Invoke the same controller and locking contract from a supervisor |

One writer per run does not mean that only one process may ever use the runtime.
Different invocations can resume the same run sequentially. A competing writer
receives a busy result instead of performing another effect. Independent run
directories have independent locks and can execute concurrently within host
capacity. Work on the same product still has to pass the existing repository,
base-revision and merge gates.

This contract assumes a local filesystem with the required lock and durability
semantics. Moving state to an arbitrary shared filesystem does not automatically
establish distributed coordination. That boundary does not make the supported
single-host deployment incomplete.

## Consumer ownership

`control_plane_core` owns deterministic authority, workflow and evidence
decisions without prescribing persistence, a database or a hosted service.
Consumers retain their existing storage and scheduling.

An existing consumer controller retains its authoritative state and runtime
adapters. Adopting shared decisions does not require replacing its storage with
the standalone runtime's JSON files, adding another controller, or introducing
a database. Consumer deployment and activation instructions remain local to
that consumer.

## Purpose of the integration additions

- Command reasoning connects an operator-selected provider to the existing
  proposal/effect boundary.
- Credential references resolve secrets when needed; an external broker is an
  optional integration, not a required vault deployment.
- A single tick can be scheduled by an existing supervisor. The provided local
  timer does not require a distributed queue.
- Local review displays the exact decision and preserves revision-bound approval.
- Usage reports describe observed attempts and outcomes. They do not introduce
  a requirement to build a commercial billing service.

Completion is judged against reliable recovery, correct authority, bounded
execution, exact approvals and verified delivery in the supported deployment.
A different hosting model or persistence backend requires a separately agreed
goal; it is not unfinished work implied by these integrations.
