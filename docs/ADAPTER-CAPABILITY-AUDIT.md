# Adapter capability audit

The upstream 1.9.2 core import aligns portable source bytes. The adapter matrix
additionally exercises the production consumer controller and
`agent_runtime.controller.Controller`. It compares their actual shared reducer
transitions, evidence invalidation and safety outcomes. Core equality alone does
not establish adapter equivalence or validate a deployed host.

## Executable contract

From either trusted full checkout:

```bash
python3 scripts/check_workflow_adapters.py \
  --reference /absolute/gitops-agent-control-plane \
  --consumer /absolute/consumer-checkout
```

The parent process verifies the consumer lock and identical portable inventories
before starting separate Python processes. Each process loads only its own
controller and test helpers. Each scenario uses temporary real Git repositories;
successful delivery executes Python product tests on the original base,
candidate and actual merge. Provider proposals and GitHub responses are controlled
peers. No live provider, GitHub service, Podman, Kotlin build or installed host is
certified by this command.

`--scenario NAME` selects a narrower reproduction. Both repositories also run
their local matrix through `tests/test_workflow_adapter_matrix.py`; their ordinary
test suite does not require the other checkout. A paired report has schema 2 and
includes each scenario's outcome and reducer trace. Different physical SHAs and
storage field names are normalized only after each adapter's exact identity
assertions pass. Unchanged risk rechecks are omitted from traces because one
adapter may perform more defensive checks; actual reroutes and invalidation are
retained.

| Scenario | Required observable behavior |
| --- | --- |
| `full-route` | Full planning and acceptance graph, real negative control and exact merged-product verification |
| `adaptive-low-route` | Reduced LOW graph retains independent executable tests, review and delivery gates |
| `negative-control-repair` | A test passing on the unchanged base is rejected; one bounded tester repair produces a valid test and verified delivery |
| `stale-review-evidence` | A stale specification binding blocks publication and leaves product main unchanged |
| `working-set-authority` | An edit outside the accepted concrete working set is rejected before candidate mutation and leaves no unrecoverable pending edit |
| `model-receipt-replay` | Restart consumes a recorded model receipt without another call or reservation |
| `uncertain-model-fence` | Restart preserves the exact unknown model effect and never dispatches it automatically |
| `ci-newer-pending` | A newer pending check supersedes an older failure without consuming a repair |
| `ci-conflicting` | Conflicting same-identity check observations stop for diagnosis |
| `ci-malformed` | Invalid check evidence stops even when another row reports failure |
| `ci-cancelled` | A cancelled newer check does not establish a product defect or authorize repair |
| `ci-latest-failure` | Only the latest trusted definitive failure enters a bounded developer repair |
| `separate-work-merge-approval` | High-risk delivery needs exactly one accepted-plan work decision and one exact-candidate merge decision; commands cannot substitute for each other |

## Drift found and corrected

The consumer previously scanned all matching CI rows for `failure` or `timed_out` after
its success check failed. An older failed run could therefore request a code
repair while a newer run was still pending; malformed or conflicting observations
could also accompany a failure. The reference runtime treated every completed
non-success as grounds for repair, including cancelled or skipped runs.

The portable `evaluate_ci_recovery` now owns this decision. It preserves the
existing `evaluate_trusted_checks` success/failure API and adds an explicit action
and latest trusted repair observations. `advance` requires success; `repair`
requires a latest `failure` or `timed_out`; missing, pending, cancelled, skipped
and neutral checks wait; malformed or conflicting evidence stops. Neither runtime
grants automatic CI rerun authority. Both adapters use the shared decision and
both execute the portable permutation tests in `ci_conformance.py`.

Work authorization and merge authorization also have different portable bindings.
Routine candidate commits within an unchanged accepted plan preserve work
authorization. Merge authority continues to bind the exact candidate. The matrix
proves the two real adapters reach the same two owner boundaries.

## Profile responsibilities and remaining coverage limits

These are adapter contracts, not missing core byte synchronization:

| Area | Consumer adapter | Operational reference adapter |
| --- | --- | --- |
| Authored authority | Immutable GitHub GoalEnvelope plus current product roadmap, selection and predecessor rules | Validated explicit goal items, dependencies and machine conditions |
| Execution state | Git-backed state/event chain, activation epochs and controller identity | Owner-held run directory, immutable receipts and runtime fingerprint |
| Provider policy | ChatGPT billing and Codex policy; bounded worker integration | Configured Codex/command providers and bounded worker integration |
| Verification | Product-specific isolated build conventions, exact CI artifacts, optional validation checkpoints | Configured isolated or explicitly trusted-local commands, JUnit and CLI predicates |
| Owner operations | Command issue and authenticated local review, service installation and transactional host upgrade | Local CLI/service API, local review, run registry and explicit quiescent upgrade |
| Plan observations | Typed baseline findings and product-authored acceptance refinements | Explicit operational plans and criteria; no consumer-specific roadmap/checkpoint schema |

Product roadmap formats, credential ownership, service installation and billing
policies stay in their adapters. Exporting shared packages does not transfer
private product authorization, deployment state, credentials or fixture IDs.
Adding a portable capability requires an explicit normalization and executable
contract in both adapters; importing the whole other runtime would not prove it.

The matrix covers representative routes and failure boundaries, not every
transport or all operator actions. Late risk escalation, base refresh, frozen-test
preservation, source retrieval, CI artifact provenance, technical recovery bounds
and upgrade transactions also have dedicated suites. Live authentication,
isolation, product builds and actual server-side governance remain target-host
validation obligations. Historical fixture success is never current operating
scope or evidence of a live upgrade.
