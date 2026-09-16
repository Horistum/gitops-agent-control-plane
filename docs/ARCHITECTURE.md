# Architecture and scope

This repository delivers a portable Python decision library and an executable,
deterministic reference. Its useful output is a tested authority/effect/evidence
contract that a production controller can reuse. It does not call a model or
provide an autonomous coding service. Tests provide finite executable evidence;
there is no theorem prover or formal verification claim.

## Implementation map

| Location | Responsibility |
|---|---|
| `control_plane_core/` | Pure decisions, graph, acceptance and evidence semantics; no provider I/O |
| `reference_runtime/_engine_impl.py` | Initialization, authority loading, selection and reconciliation |
| `reference_runtime/attempts.py` | Proposal gates, candidate creation, verification and bounded retries |
| `reference_runtime/lifecycle_effects.py` | Merge and post-effect lifecycle |
| `reference_runtime/human_decisions.py` | Revision-bound human pause and resume |
| `reference_runtime/runtime_evidence.py` | Role, cycle and summary artifacts |
| `reference_runtime/recovery_engine.py` | Durable control-state effects and recovery |
| `reference_runtime/engine.py` | Supported composition with active authority and exact identity gates |
| `reference_runtime/scenarios.py` | Trusted deterministic proposal fixtures |

The internal classes and mixins are implementation components. Call
`reference_runtime.engine` or `agentctl`; historical module-level run/resume/CLI
helpers forward to this composition. BaseEngine has no fallback proposal gate.
`contracts.py`, `probe_dsl.py` and `schema_validation.py` preserve public imports
while composing validated extensions; their private modules are not alternate
runtime profiles. New work belongs in the responsible module, not another layer
of version-numbered engines.

## Product direction

Keep one portable implementation of deterministic decisions and small adapters
that supply real observations and persist effects. Extend a core capability only
with a consuming call path or an executable adapter contract test. Model-provider,
GitHub, container and host-operation code belongs to the consuming runtime.
A new scheduler, dashboard, deployment daemon or model orchestrator is outside
this reference's scope.

## architecture

The architectural center is **goal reconciliation**, not one patch lifecycle.

Contract layers: core the core contract (see the [generated table](../README.md#contracts)), verification profile the verification profile (see the [generated table](../README.md#contracts)), runtime profile the runtime profile (see the [generated table](../README.md#contracts)).

Product authority is classified into intent, state, change, verification, and context. Each reasoning **role protocol** has explicit inputs/outputs and no Git-effect power.

Lifecycle: goal reconciliation → dependency-ready selection → discovery → bounded plan → proposals → policy/budget/risk gates → candidate → verification → computed review → feedback/repair or human authority → durable merge → post-merge verification → controller release-state effect → goal reconciliation.

The runtime uses real verification-execution and Git-effect adapter surfaces. Production hostile-code verification still requires stronger isolation than the local fixture profile.

## model

Discovery, architect, developer, test-designer, tester, and reviewer are protocol roles. Artifacts record protocol ID, item, iteration, input references, output projection, and declared powers.

Role write authority is active configuration: proposal-producing roles reference a named write envelope from policy through `config/role-protocols.json`. Reasoning roles still have no Git-effect authority.

A failed candidate can create structured feedback and another bounded attempt. In the deterministic standalone reference, the next proposal is a predeclared fixture from the bounded work catalog; the reference proves that feedback is emitted, persisted, and referenced as an input to the next attempt. It does **not** claim that the fixture was semantically generated from that feedback. A production reasoning provider is responsible for consuming the referenced feedback when producing the next proposal while preserving the same authority and evidence boundaries.

No reasoning role can merge, advance release state, approve a human gate, or sign execution evidence. Production AI providers replace role producers while preserving these boundaries.

## state-machine

The concrete standalone runtime uses these persisted phases:

`INITIALIZING → RECONCILE → DISCOVERY → BASELINE_VERIFY → PLANNING → PROPOSAL_GATES → CANDIDATE_APPLY → CANDIDATE_COMMIT → CANDIDATE_VERIFY → REVIEW → RISK_GATE`.

Review failure with remaining budget routes through durable feedback into another bounded `PLANNING` attempt. Human authority may pause at `AWAITING_DECISION` and resume with approve/reject/request_changes.

Approved work then uses two separately durable Git effects:

`MERGE_PENDING → POSTMERGE_VERIFY → CONTROL_STATE_PENDING → RECONCILE`.

`MERGE_PENDING` persists candidate merge intent before the product merge. `CONTROL_STATE_PENDING` persists the desired controller-owned release-state transition before committing it. Either pending effect can be recovered in a fresh process by stable Git trailer identity without duplicating the effect.

There are also safe **phase recovery** checkpoints after effect consumption. A restart in `POSTMERGE_VERIFY` reruns exact-revision post-merge verification; a restart in `RECONCILE` continues goal reconciliation from controller-owned release state. Neither path invents or repeats a Git effect.

From `RECONCILE`, a satisfied goal terminates at `GOAL_COMPLETED`; no dependency-ready authorized work or exhausted autonomy budgets terminate fail-closed.

## portability

V7 has three compatibility surfaces: core contract the core contract (see the [generated table](../README.md#contracts)), verification profile the verification profile (see the [generated table](../README.md#contracts)), and runtime profile the runtime profile (see the [generated table](../README.md#contracts)).

A compatible **core contract** preserves authority separation, goal semantics, role protocols, dependency-ready selection, bounded repair, human authority, durable effects, release-state transition, and reconciliation. Verification and **runtime profile** implementations may differ as long as these trust properties remain.

Candidate identity is an exact-revision property, including across durable human pauses. A human approval must be re-bound to the currently observed candidate object before effect execution, and the merge effect must consume the approved candidate revision itself rather than a mutable branch label. Merge evidence must prove the actual effect identities, for example by validating the merge parents against the expected base and candidate SHAs.

`config/contract-set.json` is a composition/version manifest, not a policy source. Policy and product authority come from their explicit authority surfaces; changing a profile identifier does not by itself grant new power.
