# GitOps Agent Control Plane

**A provider-neutral trust and governance layer for bounded software delivery
through Git, maintained by the Horistum project.**

Version 1.10.1 includes `agent_runtime`: it reads an owner-authorized goal, obtains
real proposals from an operator-selected JSON command provider or optional Codex CLI, applies bounded
edits, executes tests in rootless Podman, reviews the actual candidate, publishes
a GitHub PR, verifies trusted CI, merges by exact SHA and verifies the merge again.
The shared `control_plane_core` owns the phase, authority and acceptance decisions.

See [portable development and synchronization](docs/PORTABLE-DEVELOPMENT.md)
for the shared source and adapter validation workflow.

The separate `demo`/`loop` commands use **deterministic fixtures** to reproduce
faults and verifier limits. They do not establish AI reasoning quality. Operational
integration tests execute real Git and processes with controlled reasoning/HTTP
peers. CI also executes the lifecycle in actual rootless Podman and tests installed
package bytes. A live authenticated model turn and a particular product deployment
require their own host evidence; neither is inferred from those tests.


Embed the pure core above an existing agent, or use the supplied operational
controller. The primary integration is `reasoning.kind=command`: your adapter
owns its model API and returns data; this controller owns execution and release
authority. Codex remains supported as an explicit owner-operated alternative.
Claude, Copilot and other agents need adapters satisfying this protocol; their
unrestricted tool sessions are not automatically governed by it. The optional
[brokered Codex worker](docs/BROKERED-WORKER.md) exposes bounded controller-owned
source tools within a phase-private session. It requires explicit configuration,
a pinned CLI/schema and target-host live commissioning.

The runtime is **single-host and owner-operated**, with durable local JSON state,
effect receipts and a per-run writer lock. This is the supported storage design;
no external database is required.
Version 1.6 adds explicit credential references and a broker protocol, versioned
provider usage, a one-tick embedding API and a local exact-decision review UI.
Version 1.7 adds recoverable initialization, pre-dispatch credential checks,
nonblocking observation, a local supervisor, complete owner controls, checked backups,
and an optional installed OpenAI command adapter. Both runtimes share the same
model dispatch/replay rule. See [recovery and operations](docs/RECOVERY-170.md).
Version 1.8 adds exact-receipt reconciliation, strict adapter certification,
isolated registry errors and lossless prompt optimization with measured fixtures.
See [recovery and prompts](docs/RECOVERY-180.md).
These integrations preserve that deployment model. See
[deployment scope](docs/HOSTING.md) for storage, concurrency and consumer ownership.


## Run on your product

Python 3.11+, Git, your trusted reasoning adapter and a prepared rootless Podman
image are required for the command/GitHub profile. Supply a clean product checkout, exact path
limits, owner-authored commands, trusted CI check identities and explicit item
acceptance criteria. Examples are in [examples/operational](examples/operational).

```bash
python3 -m pip install .
agent-control doctor --policy /absolute/policy.json --goal /absolute/goal.json
agent-control start --policy /absolute/policy.json --goal /absolute/goal.json \
  --state /absolute/agent-runs/my-goal
agent-control status --state /absolute/agent-runs/my-goal
agent-control explain --state /absolute/agent-runs/my-goal
agent-control decision --state /absolute/agent-runs/my-goal
agent-control usage --state /absolute/agent-runs/my-goal
agent-control resume --state /absolute/agent-runs/my-goal
```

The same interface is available from the checkout as `./scripts/agentctl run`.
`resume` continues durable state; it does not start a fresh model conversation for
an already recorded effect. The state directory contains private source/proposal
receipts and must remain outside the product checkout.

A model may request files, exact line ranges, literal searches and bounded PR facts, propose implementation or independent tests, and
reject an actual candidate during review. The compatibility transport exposes
data only; the optional worker exposes source read/search and authorized staging
only. Neither can choose build commands, widen goal authority or approve a merge.
Required implementation permission binds the accepted work plan; required merge
permission separately binds the exact verified candidate.

The [operations guide](docs/OPERATIONS.md) covers setup, execution, approval,
recovery, image preparation and safe runtime upgrades. Local-only execution is
available for owner-trusted code with an explicit `--trusted-local` opt-in. It
cannot publish to GitHub. Its output is the run-owned `product.git`; it does not
modify the source checkout.

For the command protocol, rotating credentials, worker integration and local
review, start with the [middleware integration guide](docs/MIDDLEWARE.md).
`model_calls` reserves attempts, including uncertain outcomes; receipt-derived
usage is operational accounting, not an exactly-once billing ledger.

## Components and ownership

| Component | Responsibility |
|---|---|
| `control_plane_core` | Workflow aggregate, authority, context and typed evidence decisions; no credentials, network, process or Git effects |
| `agent_runtime` | Operational reasoning, credential resolution, GitHub, Git, verification, local persistence, embedding and owner review |
| `reference_runtime` | Versioned deterministic fixture profile and property-probe conformance demonstrations |
| Existing consumer controllers | Product-specific authority formats and service deployment; may reuse the core without running another controller |

Both operational runtimes call `development-workflow/v1` for advancement, repair,
risk escalation and evidence invalidation. The same release gate checks candidate,
integration and merged-product observations against head, base and specification.
The graph adapts to risk; independent executable verification remains mandatory.
See the [generated phase graph](docs/WORKFLOW.md) and
[operator guide](docs/OPERATOR-EXPERIENCE.md) for a readable explanation of progress,
recovery commands and the location of the run-owned result. `explain` and the
review UI combine these observations; `status --format table` and
`decision --format table` add human-readable output while JSON remains the default.
Critical/high-risk work uses the full planning and acceptance graph. Tests added by the independent
tester are executed on the original code and the candidate, then retained in the
merged product. Later items preserve earlier executed test identities and frozen
assertions. Completion requires staged acceptance and explicit machine goal
conditions, not a model's success declaration.

## Reproduce controller behavior without credentials

```bash
./scripts/agentctl demo happy-path
./scripts/agentctl loop
./scripts/agentctl demo repair-loop
./scripts/agentctl validate
```

The fixture loop demonstrates dependency-ready selection, goal reconciliation,
verification, exact merge, release-state transition and crash recovery. Its repair
proposal is prepared in advance. The operational runtime obtains each proposal
from the configured provider instead.

`raw-outcome-forgery` remains an executable **KNOWN-LIMIT** of the trusted local
property-probe profile. Rootless containers isolate operational execution from
controller credentials and receipts; finite tests, JUnit and output assertions
still do not prove arbitrary semantic correctness or defeat a compromised kernel.

## Contracts

The fixture composition's authored source is [config/contract-set.json](config/contract-set.json).
The following table, policy/schema identities and portable core constant are
generated with `python3 scripts/generate_contracts.py`; CI rejects drift.

<!-- contracts:begin -->
| Component | Contract |
|---|---|
| reference contract | `gitops-agent-control-plane/v7` |
| core contract | `autonomous-control-plane/v1` |
| verification profile | `property-probe/v6` |
| runtime profile | `standalone-local/v2` |
<!-- contracts:end -->

The operational profile is `operational-git/v1`, using the same portable core.
Policy, goal and role schemas are generated from `agent_runtime/contracts.py`
with `scripts/generate_runtime_schemas.py`; CI rejects their drift as well.

Library SemVer is separate from these wire identities. All supported decisions
are exported at the package root and through documented submodules. See the
[adoption guide](docs/ADOPTION.md) for imports, source synchronization and the
consumer compatibility gate.

## Documentation

1. [Architecture and scope](docs/ARCHITECTURE.md): purpose, implementation map and runtime boundaries.
2. [Authority and lifecycle](docs/CORE-CONTRACT.md): goals, policy, human authority and reconciliation.
3. [Verification and limits](docs/VERIFICATION.md): profiles, evidence, schema interoperability and trust boundaries.
4. [Operations](docs/OPERATIONS.md): commands, results and diagnostics.
5. [Adoption](docs/ADOPTION.md): public API, generated contracts, compatibility tests and consumer responsibilities.
6. [Middleware integration](docs/MIDDLEWARE.md): provider/credential contracts, one-tick service API, usage and local review.
7. [Deployment scope](docs/HOSTING.md): supported local storage, per-run concurrency and consumer ownership.
8. [Writing an adapter](docs/ADAPTERS.md): command-protocol checklist, credential naming registry and self-certification.

[Review remediation and validation scope](docs/REMEDIATION.md) records the changes
made after architectural review. Historical document links remain as navigation
aliases to these guides.

## Origin, license and branding

Initiated and maintained in the **Horistum GitHub organization**.
Source, documentation, schemas and examples are Apache-2.0 licensed. See
[LICENSE](LICENSE), [NOTICE](NOTICE), [TRADEMARKS.md](TRADEMARKS.md),
[release policy](docs/RELEASES.md), [maintainers](MAINTAINERS.md),
[provenance requirements](docs/PROVENANCE.md) and [publication checklist](docs/PUBLICATION.md).
A passing CI run validates its declared scope; it does not authorize public visibility.

Publication preparation in 1.9.2 adds source-policy checks, source-distribution
round-trip testing, a redacted history scan, and explicit administrator settings.
These changes do not change runtime authority, provider dispatch, receipt replay,
CLI verbs, wire contracts, or the single-host storage model.
