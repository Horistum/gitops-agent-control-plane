# Architecture and implemented scope

The repository contains one pure decision core and two concrete profiles. The
operational profile runs provider-produced work against an owner-selected product.
The older deterministic profile remains a reproducible verifier and crash laboratory.
Neither profile is a formal proof or a guarantee of model correctness.

## One domain workflow, product adapters

`control_plane_core.workflow` owns `development-workflow/v1`. Its input is a
projection of the authoritative task plus an observed event; its output names the
next phase, required planning gates and evidence groups to invalidate. It owns
the only phase graph, including repair and late risk escalation. The legacy
`next_phase` and `verification_transition` API delegate to that aggregate.

`require_workflow_evidence` is the shared release boundary for both operational
controllers. A matching head alone is insufficient: candidate tests, independent
verification, role acceptance and integration observations must match the current
base and specification. Completion also needs exact merge parents and complete
post-merge machine evidence. Authentication, test interpretation and execution
remain adapter responsibilities; neither a model statement nor a core function
can authenticate a remote check.

| Boundary | Public operational adapter | Flow adapter |
|---|---|---|
| Owner intent | Explicit JSON goal/items/typed criteria | Goal Issue plus authored YAML invariant or typed acceptanceCriteria |
| Domain decisions | `agent_runtime/workflow.py` → shared aggregate | `flow_loop/workflow.py` → identical locked aggregate |
| Authoritative state | Private fsynced state and immutable receipts | Single-writer `loop-state` Git branch and event chain |
| Provider effects | Codex/command, Git, GitHub and Podman | Existing Codex, GitHub, product, integration-log and Podman services |
| Product completion | Retained tests and verified merge | Retained tests, completion records, roadmap/lifecycle reconciliation |
| Operations | Owner CLI, pause/replan/resume | Issue projection, owner commands, activation and reviewed upgrades |

A projection is not another persisted ledger. Flow runs one controller; it does
not launch `agent-control` beside its service. Its production entry point is
`flow_loop.runtime.Controller`; historical versioned imports are compatibility
aliases. The bounded context/recovery composition is no longer a chain of
version-specific controller subclasses.

The profiles deliberately differ in deployment and authority formats. Flow's
pre-implementation high-risk approval, provider quota handling, single-writer
handoff and integration-job provenance remain stricter product/operational rules.
Those are explicit adapter policies, not alternative definitions of completion.

`control_plane_core.schema` owns the shared fail-closed JSON schema vocabulary.
The operational package does not import the fixture runtime; CI removes that
package from an installed distribution before exercising the operational loop.

## Operational composition

| Module | Responsibility |
|---|---|
| `agent_runtime/contracts.py` | Owner policy, bounded goal and phase-specific model contracts |
| `agent_runtime/controller.py` | Goal reconciliation and durable dispatch |
| `agent_runtime/workflow.py` | Storage/evidence projection into the shared aggregate |
| `agent_runtime/context.py` | Bounded retrieval and independent role views |
| `agent_runtime/roles.py` | Real role results, working sets, path gates and repair routing |
| `agent_runtime/lifecycle.py` | Negative controls, staged evidence, publication, merge and completion |
| `agent_runtime/reasoning.py` | Codex CLI or external JSON process; no direct product effects |
| `agent_runtime/git.py` | Immutable source reads, protected edits, deterministic commits and exact merges |
| `agent_runtime/verification.py` | Rootless Podman or explicitly trusted local execution; parent observations |
| `agent_runtime/github.py` | Authenticated PR/check observations, server governance and merge API |
| `agent_runtime/store.py` | One writer, fsynced state, request-bound immutable effect receipts |
| `agent_runtime/actions.py` | Owner decisions, retirement, explicit uncertain-call retry and upgrade boundary |

`operational-git/v1` is authored once as `agent_runtime.PROFILE`; its policy and
role schemas are generated from the contracts actually consumed by the controller.
The core contract identities and deterministic-profile composition remain authored
in `config/contract-set.json`. A profile identifier never grants permission.

## Authority and data flow

An owner supplies a policy and a structured goal outside the product checkout.
Both are validated and snapshotted in the private run directory. Items define
explicit dependencies, readiness, risk, source context and typed criteria. Only
items admitted by `goal_projection` may be selected by the discovery provider.
Prose explains intent; it cannot change path permissions, commands or merge limits.

The runtime obtains sources from exact Git objects. The model receives bounded
text, content hashes, phase-specific memory and actual controller observations.
It returns structured data. Only developer and tester outputs carry edits. An
architect's exact working set further narrows developer authority. The tester can
only add new files inside the independent-test envelope.

The workflow aggregate defines the complete high-assurance graph:
architect, test design, chief plan, developer, verification, tester, independent
baseline, independent candidate verification, reviewer, optional challenge,
architect acceptance, chief acceptance, publication, CI, merge and post-merge.
Low risk omits test-design/chief gates and architectural acceptance unless challenge
review requires it. Medium risk adds test design and architecture acceptance; high
risk or critical paths add the chief gates. Late escalation inserts missing gates
before another edit and reruns verification. An operator can require the full graph.

Risk is monotonic within an attempt and carried into owner replans. Ordinary
approval cannot cross the hard goal ceiling. All final diff paths must belong to
the current architect working set or the frozen independent tests. Reviews are
real provider assessments bound to the actual candidate, followed by deterministic
policy/evidence gates. A role verdict is never an execution receipt.

## Evidence and convergence

The original baseline must pass. Independent tests bind every executable
criterion to a stable JUnit identity and declare new-behavior or regression
semantics. New behavior must fail by assertion on the original source and pass
on the final candidate. Harness errors cannot establish a negative control.
Accepted assertions are frozen and retained in the product. Product repair may
change implementation but cannot rewrite those assertions.

Documentation requires the declared nonempty changed files. CI remains deferred
until authenticated trusted check results arrive; an integration criterion also
executes the exact GitHub synthetic merge after verifying both parents. Delivery
remains deferred until the actual merge passes tests and post-merge CI. Typed
machine goal conditions are evaluated after every requested item is complete.

A failed implementation routes through `repair_target` and shared verification
transitions with persisted observations. Retrieval and protocol retries have
explicit budgets. An observed trusted CI failure permits bounded implementation
repair; ambiguous harness failures stop with concrete evidence for diagnosis. Pending external work never becomes completion.

## Durability and ownership

The state directory is owned by one OS user and protected by an advisory writer
lock. Each effect persists an intent before execution. Its receipt binds run,
policy, runtime, item, attempt, turn and exact request. Receipt consumption and
phase advancement are saved together. Git commit identities are deterministic;
GitHub publication and merge reconcile server observations after lost responses.

A crash after a model response was recorded reuses it without another turn. A
crash during an unrecorded model call has an unknowable billing/result outcome;
it requires an explicit retry of the named pending effect and consumes another
call from the existing budget. No exactly-once billing claim is made.

Approvals bind base/head/specification/risk/policy/runtime/run. Merge rechecks
current identity, trusted checks and server-side governance. Only two-parent
merge commits are supported. A changed base requires a fresh attempt; it does
not inherit stale approval. A replan retires the prior attempt, keeps frozen tests
and receives a distinct branch/effect identity. Pending or merged effects cannot
be casually discarded as cancellation.

Runtime source changes invalidate resumption. Upgrade requires an authoritative
pause and no active work, or explicit suspension of a held, unchanged attempt.
It preserves the goal and history and leaves the new runtime paused. There is no
self-deployment, distributed leader election or HA controller in this profile.

## Deterministic profile compatibility

`reference_runtime` uses the fixture composition in `config/contract-set.json`.
Its responsibilities are split across selection, candidate attempts, human
pauses, lifecycle effects and evidence modules. Public `engine.py` composes all
current gates; legacy run helpers forward there. BaseEngine has no permissive
proposal fallback. The existing wrapper modules preserve old imports while
composing schema/probe extensions; they are not alternate operational entrypoints.

Its six fixture roles, checklist review and prepared repairs still prove only
that profile's controller mechanics. They are intentionally retained for fault
injection and the `raw-outcome-forgery` known limit. Operational code never imports
`reference_runtime.scenarios` or a test proposal producer.
