# GitOps Agent Control Plane Reference

**A portable decision library and a deterministic executable reference for bounded
software delivery through Git. Initiated and maintained by the Horistum project.**

Use `control_plane_core` in a controller to share authority, phase, acceptance and
evidence decisions. Run the bundled reference to inspect real local Git effects,
verification, repair and crash recovery with prepared inputs.

**The bundled reasoning roles are trusted deterministic fixtures. This repository
does not call an AI model or autonomously write arbitrary product code.** Its
architect emits a bounded template; its reviewer computes a checklist; its repair
scenario consumes a prepared next proposal. Tests demonstrate controller behavior
and finite negative properties. They are not a formal proof or evidence of model
quality. The local executor is not a hostile-code security sandbox.

## Deliverables and ownership

| Component | Responsibility | Evidence |
|---|---|---|
| `control_plane_core` | Reusable pure authority, execution, acceptance and verification decisions | Shared conformance vectors and public adapter integration tests |
| `reference_runtime` | Trusted local fixture profile with exact Git identity and durable effects | Full loop, negative, repair and fault-injection scenarios |
| Consumer runtime, including `Horistum/FlowAi-control` | Model calls, authenticated provider observations, isolation and deployment | Its own integration tests and live host gates |

The core has no network, credentials, subprocesses or Git write authority. A model
proposal grants no effect authority. Adapters supply observations; the controller
validates them and applies the permitted effect. The core is reusable inside an
existing controller and does not require a separate service.

## Start here

```bash
./scripts/agentctl demo happy-path
./scripts/agentctl loop
./scripts/agentctl demo repair-loop
./scripts/agentctl validate
```

Python 3.11+ and Git are required. `loop` runs two dependent items in the bundled
example: selection, verification, exact merge, release-state transition, and goal
reconciliation. Completion refers to the declared machine item projection;
narrative success prose remains reasoning context.

`repair-loop` proves that failed verification produces persisted feedback and a
bounded retry. The next fixture is prepared in advance. Production providers must
consume that feedback themselves and require separate verification.

## Preserved guarantees

- Reasoning roles have no direct Git-effect or release-state authority.
- Proposal paths use the shared allow/protect/deny decision and filesystem checks.
- Human `approve`, `reject` and `request_changes` act on a durable pause; approval
  is tied to the exact reviewed SHA.
- Merge uses exact base/candidate revisions and a compare-and-swap update; both
  merge parents are verified. A moved branch cannot inherit stale approval.
- Durable effect identities and Git trailers support idempotent crash recovery.
- Release progress advances only after independent post-effect verification.
- JUnit is diagnostic. Protected probes and signed parent receipts establish the
  local profile's evidence boundary.

`raw-outcome-forgery` remains an executable **KNOWN-LIMIT**: the local fixture
executor cannot protect observation of arbitrary hostile code in the same
process. Production arbitrary-code verification requires the consuming runtime's
stronger isolation and independently protected observations.

## Contracts

The authored source is [config/contract-set.json](config/contract-set.json).
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
