# GitOps Agent Control Plane

**A reusable decision core and an executable controller for bounded software
delivery through Git, maintained by the Horistum project.**

Version 1.5.0 includes `agent_runtime`: it reads an owner-authorized goal, obtains
real proposals from Codex or a configured JSON command provider, applies bounded
edits, executes tests in rootless Podman, reviews the actual candidate, publishes
a GitHub PR, verifies trusted CI, merges by exact SHA and verifies the merge again.
The shared `control_plane_core` owns the phase, authority and acceptance decisions.

The separate `demo`/`loop` commands use **deterministic fixtures** to reproduce
faults and verifier limits. They do not establish AI reasoning quality. Operational
integration tests execute real Git and processes with controlled reasoning/HTTP
peers. CI also executes the lifecycle in actual rootless Podman and tests installed
package bytes. A live authenticated model turn and a particular product deployment
require their own host evidence; neither is inferred from those tests.

## Run on your product

Python 3.11+, Git, a supported Codex CLI and a prepared rootless Podman image are
required for the Codex/GitHub profile. Supply a clean product checkout, exact path
limits, owner-authored commands, trusted CI check identities and explicit item
acceptance criteria. Examples are in [examples/operational](examples/operational).

```bash
python3 -m pip install .
agent-control doctor --policy /absolute/policy.json --goal /absolute/goal.json
agent-control start --policy /absolute/policy.json --goal /absolute/goal.json \
  --state /absolute/agent-runs/my-goal
agent-control status --state /absolute/agent-runs/my-goal
agent-control resume --state /absolute/agent-runs/my-goal
```

The same interface is available from the checkout as `./scripts/agentctl run`.
`resume` continues durable state; it does not start a fresh model conversation for
an already recorded effect. The state directory contains private source/proposal
receipts and must remain outside the product checkout.

A model may request files, exact line ranges, literal searches and bounded PR facts, propose implementation or independent tests, and
reject an actual candidate during review. It cannot execute tools, choose build
commands, widen goal authority or approve a merge. Human approval, when required
by the configured risk and merge limits, names the exact current candidate binding.

The [operations guide](docs/OPERATIONS.md) covers setup, execution, approval,
recovery, image preparation and safe runtime upgrades. Local-only execution is
available for owner-trusted code with an explicit `--trusted-local` opt-in. It
cannot publish to GitHub. Its output is the run-owned `product.git`; it does not
modify the source checkout.

## Components and ownership

| Component | Responsibility |
|---|---|
| `control_plane_core` | Workflow aggregate, authority, context and typed evidence decisions; no credentials, network, process or Git effects |
| `agent_runtime` | Operational reasoning, GitHub, Git, verification, persistence and owner-command adapters |
| `reference_runtime` | Versioned deterministic fixture profile and property-probe conformance demonstrations |
| Consumers such as `FlowAi-control` | Product-specific authority formats and service deployment; may reuse the core without running another controller |

Both operational runtimes call `development-workflow/v1` for advancement, repair,
risk escalation and evidence invalidation. The same release gate checks candidate,
integration and merged-product observations against head, base and specification.
The graph adapts to risk; independent executable verification remains mandatory.
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

[Review remediation and validation scope](docs/REMEDIATION.md) records the changes
made after architectural review. Historical document links remain as navigation
aliases to these guides.

## Origin, license and branding

Originally developed and published from the **Horistum GitHub organization**.
Source, documentation, schemas and examples are Apache-2.0 licensed. See
[LICENSE](LICENSE), [NOTICE](NOTICE), [TRADEMARKS.md](TRADEMARKS.md),
[release policy](docs/RELEASES.md) and [publication checklist](docs/PUBLICATION.md).
