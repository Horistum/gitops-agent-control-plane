# Shared execution, core 1.2.0

`control_plane_core/execution.py` defines pure phase/repair transitions, strict
observed retry preconditions, bounded revision-bound phase-private memory,
recovery availability, attempt numbering, retirement and safe upgrade decisions.
`acceptance.py` classifies exact criterion IDs and evaluates only obligations due
at the current stage. Neither module performs effects or trusts model assertions
as observations. Flow 0.6.0 consumes these exact files through its core lock.

## Executable profile coverage

| Obligation | Standalone reference | Flow production adapter |
|---|---|---|
| behavior | Exact acceptance probes fail on original base and pass on candidate | Frozen independent tests with fail-on-base/pass-on-candidate observations |
| compatibility | Declared probes pass on both revisions | Regression bindings pass on both revisions |
| documentation | Exact nonempty UTF-8 Git blobs at candidate/merge revisions | Exact document paths/hashes plus semantic role review |
| ci | Rejected before execution: no hosted CI adapter in standalone-local/v2 | Trusted named checks and Flow integration checkout evidence |
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

## Regression boundary

Both repositories run identical execution and acceptance conformance cases.
`tests/test_typed_execution.py` runs the public autonomous reference engine on a
real local fixture, covering mixed criteria, pre-merge deferral, post-merge
completion, missing-document failure and unsupported hosted-CI rejection.
Flow additionally tests the production facade with an AR-04C-derived identity
collision scenario, nine mixed criteria, stateless model retrieval, durable
restart, retained tests and real local Git merges. Model and GitHub transport
are controlled test adapters. Actual Codex and Kotlin/Podman builds remain host
deployment gates; these tests make no live deployment claim.
