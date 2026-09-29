# Adopting the shared controller domain

An existing controller can reuse the pure `control_plane_core` without launching
a second controller, replacing its persistence, or adopting the supplied runtime.
Alternatively, use `agent_runtime` for its documented owner-operated lifecycle.
Consumer-specific deployment instructions and private validation records belong
in the consumer repository, not in this public reference.

## Supported API

The current version is exported as `control_plane_core.__version__` and declared
in `pyproject.toml`. Supported decisions are exported from the package root and
from `workflow`, `decisions`, `execution`, `acceptance`, `verification`, `schema`,
`usage`, `authorization` and `prompting`, each with explicit public exports. No runtime dependency
or reference configuration is required to import the pure core.

The distribution also contains the optional `agent_worker`, `agent_runtime`,
`reference_runtime`, and the
`agent-control` CLI. Importing the core does not require deploying those runtimes.
The phase graph includes independent execution on the original code before
candidate verification. Missing specification identity or candidate test errors
cannot become successful acceptance.

## One authored contract manifest

Edit [config/contract-set.json](../config/contract-set.json), then run:

```bash
python3 scripts/generate_contracts.py
python3 scripts/generate_contracts.py --check
```

The generator projects identities into policy, schemas, README and the core.
Operational schemas are generated from `agent_runtime/contracts.py` using
`scripts/generate_runtime_schemas.py`. CI rejects drift. Library SemVer is
independent of wire versions; see [RELEASES](RELEASES.md).

## Consumer compatibility gate

The generic gate takes a trusted, exact, clean consumer checkout, copies it into
temporary storage, overlays the reviewed core, and runs that consumer's tests.
It never deploys or edits the original consumer checkout.

```bash
python3 scripts/check_consumer.py --consumer /absolute/consumer-checkout   --expected-commit FULL_CONSUMER_SHA   --output /absolute/private-audit/consumer-compatibility.json
```

It records the consumer commit, core hashes, command, test count and result.
Keep reports/logs private when they expose a private product. A passing source
compatibility run is not proof that a consumer integrates every workflow stage
or that its live installation is updated. Test actual event/adapter integration
and activation separately; no private consumer is a prerequisite for this
repository's normal validation or distribution checks.

## adoption

### 1. Classify authority

Separate intent, authoritative state, change authority, verification authority,
and reasoning context. The example `.agent-control/authority-model.json` is
product-owned. Other formats may be normalized into the same contract; models
cannot convert descriptive text into authority or own the controller's ledger.

### 2. Preserve authored goal semantics

Machine-enforced item selection, budgets, paths and acceptance criteria must be
explicit. Prose such as objectives remains reasoning context unless a documented
predicate gives it executable semantics. Missing evidence types must not be
silently weakened. Model refinements are extra obligations, not replacements
for the owner's criteria.

### 3. Keep proposal and effect authority separate

A model may propose edits, tests, plans or a rejection, but cannot choose arbitrary
build commands, modify policy, publish or approve a merge. Configure exact write
boundaries and trusted verification commands. Preserve independent role inputs,
frozen assertions and revision-bound review.

### 4. Select the correct profile

The deterministic profile uses trusted local fixtures and property probes. It is
not a hostile-code sandbox and retains the documented `raw-outcome-forgery`
known limit. The operational profile uses bounded providers, rootless Podman,
GitHub checks and exact merges. Finite tests cannot establish universal semantic
correctness. See [VERIFICATION](VERIFICATION.md) and [OPERATIONS](OPERATIONS.md).

### 5. Preserve exact revision identities

Bind execution evidence and merge approvals to head, base, specification, goal
and policy. Bind implementation permission to the accepted plan and concrete scope
independently of its moving implementation head. Verify both merge parents and the actual merged product. A base refresh or replan
invalidates old evidence and approvals. Use provider-side protected-ref or
compare-and-swap mechanisms; never infer completion from a model declaration.

### 6. Keep recovery bounded

Record effect intent before dispatch and durable receipts before advancing.
Replay an existing receipt without resolving credentials or calling the model
again. An uncertain paid call is not an automatic retry. Replanning must not reset
the lifetime budget or replace frozen independent tests. Reconcile an observed
merge before cancellation or retirement.

## shared-core

`control_plane_core` is the canonical portable implementation. A consumer may
vendor an exact reviewed snapshot using `CONTROL-CORE.lock.json` and the supplied
synchronization tool. Schema 2 also covers optional worker and contract tooling.
Shared changes may originate in a trusted development consumer and be exported
back into this reference; see [portable development](PORTABLE-DEVELOPMENT.md). The lock retains file hashes, source commit, version,
contract, Apache license and NOTICE. It is not a runtime auto-update mechanism.

| Concern | Pure core | Consumer responsibility |
|---|---|---|
| Selection | Validated dependency graph and bounded scope | Authenticate and normalize owner intent |
| Completion | Verified, scoped transitions and goal predicates | Obtain and persist actual execution/merge observations |
| Risk/approval | Monotonic risk and exact decision requirements | Authenticate human decisions and enforce host policy |
| Changes | Path and proposal envelopes | Filesystem safety, source identity and applying edits |
| CI/merge | Exact revision and trusted check decisions | Authenticated provider APIs and protected merge operations |
| Recovery | Bounded attempts, replay and upgrade decisions | Durable storage, locking and effect reconciliation |

The core has no process, network, credential or Git side effects. Passing a
provider's claimed success boolean to it does not authenticate an observation.
Different consumers may impose stronger operational rules but must not bypass
the shared release gate or reinterpret incomplete evidence as completion.

### Reproducible adoption

```bash
python3 scripts/sync_control_core.py --source /absolute/reference-checkout   --target /absolute/consumer-checkout --commit FULL_REFERENCE_COMMIT
cd /absolute/consumer-checkout
python3 scripts/sync_control_core.py --check
python3 -m unittest discover -s tests -v
```

The consumer must provide the synchronization/check tooling it adopts. Review
those ordinary source changes and run consumer CI before deployment. A newer
reference commit does not automatically change a source lock or live service.
Source synchronization rejects linked or locally diverged portable packages.
Initial unmanaged targets require identical reviewed bytes and explicit adoption;
see the two-commit provenance procedure in the portable development guide.

### Validation boundary

`python3 -m control_plane_core.conformance` exercises the pure contract.
`./scripts/agentctl validate` also runs operational integration tests and all
fixture scenarios. Actual model authentication, provider quota, product build
images, consumer acceptance and host activation remain deployment checks.
Optional consumer-specific adapter comparison helpers are not invoked by the
public validation path and are not evidence of an inaccessible consumer's state.

## shared-execution

`execution.py` owns phase/repair transitions, revision-bound memory and retry,
retirement and safe-upgrade decisions. `acceptance.py` classifies exact criterion
IDs and evaluates obligations only at their required stage. Neither performs
effects or trusts a model claim as authenticated evidence.

| Obligation | Deterministic profile | Operational profile |
|---|---|---|
| Behavior | Acceptance probes fail on base and pass on candidate | Frozen independent tests with actual negative controls |
| Compatibility | Declared probes pass on both revisions | Retained regression test identities and assertions |
| Documentation | Exact nonempty UTF-8 Git blobs | Exact paths/hashes plus role review |
| CI | Rejected where hosted CI is unavailable | Required App/name/revision checks and integration execution |
| Delivery | Exact merge and executed post-merge probes | Protected merge, required checks and merged-product verification |

Future obligations remain deferred, not complete. Unknown types or missing
bindings cannot borrow a weaker evidence class. Accepted independent tests are
retained and later items preserve prior executed identities and assertions.
The public `tests/test_adapter_integration.py` and runtime suites exercise these
boundaries with real Git/process operations and explicitly controlled providers.
