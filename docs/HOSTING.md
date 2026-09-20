# Hosting decision: middleware now, multi-tenant service as a separate migration

The deployable product in this repository is a provider-neutral governance core
and an owner-operated runtime. It is not a horizontally scalable SaaS backend.
There is no PostgreSQL backend, distributed queue, managed tenant registry or
enterprise identity service in 1.6.0. No configuration switch enables those claims.

## Findings checked against the implementation

| Area | Implemented | Remaining hosted requirement |
|---|---|---|
| State | Local fsynced JSON, per-run advisory lock, durable intents/receipts | Transactional tenant-scoped database, concurrency control and migration |
| Workspace | Private bare Git repository and local snapshots | Host-affine workers or verified portable object/workspace storage |
| Reasoning | Default command example, legacy/v2 protocol, optional Codex | Operated vendor adapters, quota controls, provider policies and tenant routing |
| Credentials | Late environment/broker references, per-request REST resolution | Authenticated secret service, tenant authorization, rotation/revocation operations and Git transport isolation |
| Scheduling | Bounded one-step service/CLI, explicit busy outcome, sample local timer | Durable queue, signed webhooks, scheduler, fairness and distributed worker ownership |
| Approval | Shared exact document, loopback UI, stale-document rejection | SSO/RBAC, separation of duties, trusted actor identity and remote session protection |
| Accounting | Receipt-derived reservations, outcomes and optional token usage | Billing ledger, external reconciliation, prices, disputes and retention |
| Execution | Rootless Podman resource/network restrictions | Threat model and isolation for hostile tenants across host, credentials, caches and control plane |

Three optimistic assumptions need correction. A reserved model attempt is not
necessarily a successful or billable call. An effect receipt does not establish
exactly-once delivery to a remote system or a tamper-proof invoice. Rootless
containers reduce privileges but still share a host/kernel and do not isolate
controller processes, provider executables or host Git credentials across tenants.

## Required persistence migration

Replacing `Store.save()` alone is insufficient: locking is also used by start,
tick, owner actions, upgrade and service reads. Receipts and `product.git` are
local dependencies. A future storage interface must encompass those lifecycle
operations, not merely JSON serialization. Preserve the pure core; implement
storage and effect execution in the host adapter.

Suggested database ownership (design only; not a shipped schema):

| Entity | Tenant-scoped identity | Required invariant |
|---|---|---|
| Run | `(tenant_id, run_id)` | Versioned authority snapshot, state version and active worker generation |
| Effect intent | `(tenant_id, run_id, effect_id)` | Unique immutable request hash and reserved budget before any dispatch |
| Receipt | `(tenant_id, run_id, effect_id)` | Immutable result hash; a conflicting insert fails rather than overwrites |
| Owner decision | `(tenant_id, run_id, decision_id)` | Authenticated actor plus exact binding/document/version |
| Wake-up/outbox | `(tenant_id, event_id)` | State change and delivery intent committed together |
| Usage event | `(tenant_id, effect_id, event_kind)` | Idempotent accounting event, with unknown outcomes explicitly preserved |

Every query and uniqueness constraint must include tenant scope. Derive the scope
from authenticated server context; never trust a client-provided tenant string,
run path or broker reference. Tenant isolation tests must include guessed IDs,
reused effect hashes, background jobs, support access and backups.

Use optimistic state versions (`UPDATE ... WHERE version = expected`) inside a
transaction, together with budget reservation and the unique effect intent. Do
not hold a database transaction open across a model/build/network call. Perform
the external effect outside the transaction. Commit the receipt, next state and
outbox/accounting events atomically after verifying worker ownership/version.
The database's committed durability replaces fsync semantics; deployment must
also specify WAL, backup, recovery and failover durability targets.

An expiring lease alone cannot stop an old worker from completing a remote write.
Use ownership generations/fencing at the executor boundary, effect identity and
operation-specific reconciliation. Where a provider cannot reject an old worker
or deduplicate a request, preserve uncertainty and prevent automatic duplicate
dispatch. A successful database CAS after a duplicate remote write does not repair
the duplicate. Test this failure explicitly for model calls, PR creation and merge.

Plan Git persistence separately. Workers may remain pinned to an isolated host
with a durable volume, or rebuild verified Git objects/workspaces from protected
storage. A new worker must prove base/head/object and receipt identity before
resumption. Do not put `product.git` on an arbitrary shared filesystem and assume
the old `flock` contract has become distributed locking.

## Scheduling and authorization

Webhooks are wake-up hints, not authority or completion evidence. Verify signatures
and installation/repository scope, deduplicate deliveries, then enqueue trusted
run IDs. Re-observe provider state before acting. Add timer-based recovery of lost
events, bounded retries/backoff, dead-letter handling, per-tenant quotas and
fairness. Do not acknowledge completion merely because a worker was dispatched.

A worker first resolves tenant/run/credential scope from server configuration,
then acquires ownership, then invokes the runtime adapter. Never accept policy
commands, filesystem paths or credential references from an unauthenticated job.
The current `RunService` offers a clean call site but retains the local writer lock;
it is not a distributed ownership implementation.

For enterprise approval, the authenticated server must determine the actor and
permissions; a submitted actor name is not proof. Render the complete immutable
decision snapshot, then compare its fingerprint and candidate binding within the
same authorized transaction that records approval. Preserve actor, timestamp,
tenant, role, decision and evidence retention. Test revoked permissions, concurrent
reviews, changed findings, changed base, replayed sessions and cross-tenant IDs.
The current local bearer UI intentionally represents only the OS owner's authority.

## Credential and execution isolation

Prefer a model API adapter for hosted operation. An optional Codex profile should
remain an explicitly chosen account-owned deployment with a dedicated authenticated
directory; do not multiplex unrelated tenants through one `codex_home`. Any managed
account flow needs separate lifecycle, access and provider-policy review.

The generic broker protocol is an integration seam, not a vault implementation.
The operated broker must authenticate workers, scope secrets to tenant/repository/
provider, supply short-lived credentials where supported, revoke and rotate them,
and provide audit records without secret values. Cover Git HTTPS/SSH separately
from GitHub REST. Never place model adapters or brokers under tenant write access.

For mutually untrusted tenants, select an isolation model for workers and builds
(for example isolated VMs or stronger dedicated execution boundaries) and validate
it against the workload. Include cache sharing, local sockets, filesystem paths,
image trust, egress, CPU/memory/PID quotas and host compromise in that evaluation.
This repository's local tests are not a cross-tenant penetration test.

## Delivery gates and product choice

1. **Embedded middleware (implemented):** provider-neutral core, explicit command
   boundary, credential references, local accounting, single-step service and
   exact local approval. Validate legacy/v2 providers, crash replay, rotated
   secrets, lock contention and stale approval rejection.
2. **Managed isolated installations (deployment work):** provision separate owner
   boundaries, credentials, volumes, monitoring, upgrade/backup and recovery per
   customer. This avoids pretending a local store is a shared SaaS backend, but
   requires real operational ownership and capacity planning.
3. **Shared hosted service (not implemented):** ship database migration plus real
   PostgreSQL rollback/CAS/crash/failover tests, executor fencing, durable queue,
   tenant identity/authorization, enterprise review, vault integration and billing
   reconciliation. Restore backups and exercise cross-tenant denial before release.

Require an offline migration with source checksums, preserved receipt IDs and
budgets, dry-run verification and rollback to the untouched local snapshot. Never
run old and new controllers as concurrent writers during cutover. Preserve runtime
upgrade/approval invalidation semantics; do not relabel in-flight authority.

Size hosted delivery after choosing isolation, authentication, Git storage and
provider requirements. A generic months/team estimate is not an implementation
plan or evidence of production readiness. The middleware is a reusable component
of Horistum and FlowAI-Control; no separate competing SaaS product is assumed.
