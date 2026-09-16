# Adopting and testing the shared core

## Supported API

Core library 1.3.0 exposes all supported decisions from `control_plane_core` and
from `decisions`, `execution`, `acceptance`, and `verification`. Each module has an
explicit `__all__`; submodule imports remain supported. The source package has
no runtime dependencies and needs no reference repository configuration when
installed on its own.

The role graph now includes the independent baseline before independent candidate
verification. Missing specification identity and candidate test errors fail
acceptance. These are safety corrections; run consumer tests before updating its
pinned source bytes.

## One authored contract manifest

Edit `config/contract-set.json`, then run:

```bash
python3 scripts/generate_contracts.py
python3 scripts/generate_contracts.py --check
```

The command generates identity projections in the policy, schemas, README and
portable core constant. Validation rejects drift. Library SemVer remains in
`pyproject.toml` and `control_plane_core.__version__`; it is independent of the wire
contracts. Documentation refers to the generated README contract table instead
of requiring manual version replacement across guides.

## Consumer compatibility gate

A reusable gate copies an exact clean consumer checkout into temporary storage,
overlays the current core and executes its tests. It never edits the original
checkout, synchronizes remote branches, deploys a service, or substitutes its
result for the consumer release/activation gates.

```bash
python3 scripts/check_consumer.py --consumer ../FlowAi-control \
  --expected-commit FULL_CONSUMER_SHA --output consumer-compatibility.json
```

The JSON report records the consumer revision, current core file hashes, command,
exit status and test counts. Archive it with the release evidence. The current
reference's CI cannot promise the state of a private consumer that it cannot
read; run this gate whenever either side changes. The public adapter integration
tests remain runnable without access to that repository.

## adoption

Treat the repository as a composition of a core control-plane contract plus replaceable verification/runtime profiles. Do not start by wiring an LLM to the local executor and hoping the surrounding invariants somehow materialize. Humans have tried this general technique with distributed systems too, with memorable results.

### 1. Classify authority first

Before connecting a reasoning provider, identify which product artifacts are:

- intent authority;
- state authority;
- change authority;
- verification authority;
- reasoning context.

The reference `.agent-control/authority-model.json` is a product-owned authority manifest. Adaptations may use other artifact names, but the core invariant remains: reasoning cannot silently convert context into machine policy or take ownership of controller state.

### 2. Define goal semantics honestly

Classify each goal field according to what the controller actually does with it. In v1, `items`, risk/merge/autonomy bounds, and forbidden paths are machine enforced. `objective`, `success_condition`, and `forbidden_directions` are reasoning context.

If a product needs an executable success predicate beyond completion of authorized roadmap items, define a typed predicate contract or a new core profile. Do not label prose as verified merely because an evidence artifact repeats it.

### 3. Bind roles to real authority

`config/role-protocols.json` is active in the reference runtime. Proposal-producing roles resolve `product_write_power` to concrete policy path envelopes; roles with `none` cannot submit product changes. No role receives Git effect power.

For another system, preserve that separation even if role names differ. A model may propose a patch, a test, or a plan, but the controller applies policy and owns side effects.

### 4. Choose a verification profile

the verification profile (see the [generated table](../README.md#contracts)) supports multiple positional args, generated named kwargs, bounded generators, exception or return-equality oracles, and a generic expression language. Static validation rejects references to nonexistent args/kwargs, incompatible `length` operands, and expressions deeper than the supported bound before candidate execution begins.

The DSL is intentionally limited. If a product needs richer invariants, extend or replace the verification profile rather than embedding product-specific Python callbacks in the generic control plane.

### 5. Choose a runtime profile

the runtime profile (see the [generated table](../README.md#contracts)) uses local Git and trusted deterministic fixture processes. It demonstrates effect identity, resume semantics, bounded process execution, and conformance mechanics. It is not a hostile-code sandbox.

A production runtime for model-generated arbitrary code needs stronger isolation such as container, VM, or remote verification boundaries and a result channel outside candidate control.

### 6. Preserve revision identity

Human and automatic effects should name exact immutable revisions. A human approval is valid only for the reviewed SHA. The reference re-resolves the mutable candidate branch before approval, performs an exact-SHA merge, verifies both merge parents, and retains candidate commits under audit refs even when working branches are deleted.

Production GitHub/GitLab adapters should preserve the same property using provider-native compare-and-swap or protected-ref mechanisms.

### 7. Re-run preconditions on repair

Persist verification feedback and route bounded repair attempts, but never assume old preconditions apply to a new base revision. After `request_changes`, rerun baseline verification, completed-item regressions, and acceptance negative control before the next proposal attempt.

### 8. Reconcile after every verified effect

Make human approve/reject/request_changes resumable. Make both product merge and controller progress updates durable effects. After every verified progress transition, reload authority/release state and reconcile until the requested objective projection is satisfied or authority is exhausted.

### 9. Keep evidence auditable

Evidence that names a candidate SHA should retain that Git object. Negative fixtures should remain readable enough that a reviewer can verify the attack path without mentally unescaping a thousand-character source literal. Schema coverage and conformance assertions should prove properties, not merely count files.

## shared-core

The canonical reusable implementation is `control_plane_core`; its version is
exported as `control_plane_core.__version__`. The standalone engine imports it
directly. `Horistum/FlowAi-control` vendors a reviewed snapshot named in
`CONTROL-CORE.lock.json`. Publishing a new reference version does not update that
consumer pin or its live installation.

### Ownership

| Concern | Shared implementation | Runtime responsibility |
|---|---|---|
| Work selection | Validated dependency graph, readiness, bounded requested scope | Read and authenticate product intent; normalize JSON or Flow YAML |
| Completion | Verified, scoped, idempotent completion and goal projection | Persist progress only after exact merge and post-merge verification |
| Risk | Hard risk ceiling, automatic merge ceiling, mandatory human threshold | Authenticate revision-bound human decisions |
| Changes | Relative path and allow/protect/deny decisions | Validate expected bytes, size, filesystem boundaries and apply proposals |
| Merge | Exact base/candidate and two-parent identity proof | Local Git CAS or protected GitHub merge API; durable operation intent |
| Execution | Phase transitions, repair routing, retry preconditions, bounded memory and attempt identity | Execute, observe and durably persist effects under the runtime profile |
| Acceptance | Exact criterion typing and stage evaluation | Obtain real test, document, CI and merge observations |
| CI | Latest successful named check from the configured provider identity | Obtain check observations from authenticated provider APIs |

The core has no process execution, Git writes, network, credentials or model
provider. Models cannot directly create effect authority. The runtime adapter
must obtain observations from the declared trusted source; passing a model's
claimed `verification_passed` boolean does not constitute verification.

`goal_projection()` without an intent graph computes completion only and grants
no selection authority. Prose remains reasoning context. A risk above the hard
goal ceiling is blocked; ordinary approval cannot enlarge that goal.

### Deliberate profile differences

The reference uses the verification profile (see the [generated table](../README.md#contracts)), fixture providers, retained candidate audit
refs, local Git and controller-owned `release-state.json`. Flow uses a Codex
provider, rootless Podman, protected GitHub PRs and durable `loop-state`. Its
product-authored YAML release metadata is a lifecycle assertion, not the
controller's completion ledger. Its `flowai-yaml/v1` profile normalizes declared
dependencies and ordered implementation slices and verifies external predecessor
merges against the current base and trusted post-merge checks.

The fixture retains its property-probe negative controls and promotion. Since core 1.2.0, the library also supplies `verification-evidence/v1`: executable AC/test bindings, declared new-behavior versus regression semantics, typed goal conditions and externally evaluated process/artifact predicates. Flow 0.6.0 uses these with its counterfactual/regression and rootless CLI adapters, promotes accepted independent test files, and verifies the actual merge again.

The reference also provides `agentctl verify-cli --trusted-fixture` as a separately runnable external process observation profile. This command is not a production sandbox and does not replace the standalone engine's configured property-probe profile. `docs/LIMITATIONS.md`, including raw-outcome-forgery, remains applicable to that legacy profile. Finite external observations do not prove every possible product behavior.

### Reproducible adoption

On a clean checkout of a reviewed reference commit:

```bash
python3 scripts/sync_control_core.py --source . --target ../FlowAi-control --commit FULL_REFERENCE_COMMIT
cd ../FlowAi-control
python3 scripts/sync_control_core.py --check
python3 -m unittest discover -s tests -v
python3 scripts/build_release_manifest.py
```

The synchronization is a development operation, never a runtime auto-update.
Review the consumer changes and run CI before deployment. The script rejects a
dirty source, non-exact revision, linked package or a locally diverged consumer.
The lock inventories all core files and retains the Apache license and NOTICE.
Both repositories execute the same `control_plane_core.conformance` vectors,
plus their runtime integration suites. The consumer fingerprint includes the
core and its nested runtime dependencies, so core changes invalidate activation.

### Validation boundary

`python3 -m control_plane_core.conformance` tests the pure contract.
`./scripts/agentctl validate` also exercises the standalone state machine,
security scenarios and crash recovery. Flow's full suite exercises its adapters
and real local Git interactions. A live Legion installation, live Codex response
and real Flow product build remain deployment gates on that host.

The executable typed reference profile and Flow adapter coverage are documented in
[SHARED-EXECUTION.md](SHARED-EXECUTION.md).

## shared-execution

`control_plane_core/execution.py` defines pure phase/repair transitions, strict
observed retry preconditions, bounded revision-bound phase-private memory,
recovery availability, attempt numbering, retirement and safe upgrade decisions.
`acceptance.py` classifies exact criterion IDs and evaluates only obligations due
at the current stage. Neither module performs effects or trusts model assertions
as observations. Flow consumes its own reviewed version of these files through its core lock.

### Executable profile coverage

| Obligation | Standalone reference | Flow production adapter |
|---|---|---|
| behavior | Exact acceptance probes fail on original base and pass on candidate | Frozen independent tests with fail-on-base/pass-on-candidate observations |
| compatibility | Declared probes pass on both revisions | Regression bindings pass on both revisions |
| documentation | Exact nonempty UTF-8 Git blobs at candidate/merge revisions | Exact document paths/hashes plus semantic role review |
| ci | Rejected before execution: no hosted CI adapter in the local profile | Trusted named checks and Flow integration checkout evidence |
| delivery | Exact two-parent merge and executed post-merge probes | Protected merge identity, checks and repeated post-merge product execution |

Every accepted criterion retains its original text and exact ID. Absent typing
keeps legacy behavior semantics; it never guesses a weaker kind from prose.
Future obligations are `deferred` before their stage, not completed or ignored.
A candidate may pass its due obligations without being a completed delivery.
The public engine records `typed-acceptance-evaluated` events before merge and
after actual merge execution. Failure of a required document blocks review;
future delivery becomes complete only with observed merge and post-merge probes.

Native roadmap example (alongside the existing behavior criteria):

```json
[
  {"id":"AC-COMPAT","text":"Retain normalization","kind":"compatibility","probe_ids":["baseline-normalize"]},
  {"id":"AC-DOC","text":"Describe semantics","kind":"documentation","probe_ids":[],"paths":["README.md"]},
  {"id":"AC-DELIVERY","text":"Merge and verify","kind":"delivery","probe_ids":[]}
]
```

Probe IDs must actually exist in the product's declared verification probes.
Non-test criteria cannot borrow test bindings. The canonical normalizer supplies
controller-owned stages and validates all selectors. The standalone engine still
uses its declared property-probe trust boundary; finite probes do not establish
arbitrary semantic correctness or production sandbox isolation.

### Regression boundary

Both repositories run identical execution and acceptance conformance cases.
`tests/test_typed_execution.py` runs the public autonomous reference engine on a
real local fixture, covering mixed criteria, pre-merge deferral, post-merge
completion, missing-document failure and unsupported hosted-CI rejection.
Flow additionally tests the production facade with an AR-04C-derived identity
collision scenario, nine mixed criteria, stateless model retrieval, durable
restart, retained tests and real local Git merges. Model and GitHub transport
are controlled test adapters. Actual Codex and Kotlin/Podman builds remain host
deployment gates; these tests make no live deployment claim.
