# Verification, evidence and trust boundaries

## What the evidence establishes

| Layer | Executed here | Evidence boundary |
|---|---|---|
| Core conformance | Shared pure functions and invalid inputs | Decision semantics for supplied observations |
| Adapter integration | Real local Git, exact revisions, external Python processes, counterfactual, repair and postmerge | Local adapter composition; role and hosted-CI responses are test doubles |
| Reference scenarios | Fixture proposals, protected probes, bounded loop and injected crashes | Reproducible controller behavior, not model reasoning |
| Consumer compatibility | `scripts/check_consumer.py` against an exact clean consumer checkout | That checkout's tests with current core; no live provider or deployment claim |
| Live installation | Not run by this repository | Codex, Podman, authenticated GitHub and product build gates remain consumer/host responsibilities |

`tests/test_adapter_integration.py` exercises the longer shared graph, real process
failure/repair, revision-scoped persisted context, exact two-parent merge, CAS
rejection and postmerge completion. The fixture engine deliberately uses a
smaller profile; an API listed in the shared core is not implicitly exercised by
every runtime profile.

## JSON Schema compatibility

Published schemas use a deliberately supported subset of JSON Schema Draft
2020-12. They remain valid standard schemas. The local validator rejects unknown
keywords, including nested unused schemas, instead of silently ignoring them.
It handles JSON equality (boolean versus number, numeric 1 versus 1.0), integer
semantics and substring regex matching. Published identity patterns explicitly
anchor the entire string, preserving exact SHA boundaries.

CI compares supported cases and every published schema against `jsonschema` via
`tests/test_schema_interoperability.py --require-reference`. This dependency is
used only in development. Full vocabulary support, arbitrary regular-expression
dialects and schema composition are not promised. Before adding a keyword,
extend the validator and differential tests or deliberately adopt a full runtime
validator. See the [validation specification](https://json-schema.org/draft/2020-12/json-schema-validation).

## verification

The configured verification profile in the [generated table](../README.md#contracts) retains generic invariant probes, case-level negative control, exact revision binding, HMAC parent receipts, non-authoritative JUnit, current receipt-injection regression, and executable raw-outcome known-limit reproduction. Completed item acceptance probes become regression probes in later autonomous cycles.

## profiles

The standalone reference is a composition of three independently versioned surfaces:

the core contract (see the [generated table](../README.md#contracts)) + the verification profile (see the [generated table](../README.md#contracts)) + the runtime profile (see the [generated table](../README.md#contracts)) = the reference contract (see the [generated table](../README.md#contracts)).

### Core contract

the core contract (see the [generated table](../README.md#contracts)) defines authority classes, goal semantics, reasoning-role boundaries, dependency-ready selection, bounded repair, human decisions, exact-revision effects, durable controller progress, recovery, and outer goal reconciliation.

Changing a verifier transport or Git provider does not require changing this core if those invariants remain true.

### Verification profile

the verification profile (see the [generated table](../README.md#contracts)) defines the standalone generated-case/invariant mechanism, negative controls, signed verifier receipts, and exact-revision verification evidence. The executable `raw-outcome-forgery` known limit belongs to this verification/runtime boundary, not to the generic autonomous core.

A different verifier may replace this profile if it preserves the verification authority expected by the core.

### Runtime profile

the runtime profile (see the [generated table](../README.md#contracts)) defines local Git/process adapters, deterministic role fixtures, process timeouts, exact-SHA merge mechanics, and local durable recovery. A GitHub, GitLab, Jenkins, Tekton, or Argo-backed implementation would be another runtime profile.

### `contract-set.json` is a compatibility manifest

`config/contract-set.json` is the machine-readable **implementation composition manifest**. It is intentionally exact for this reference implementation. It is not operator configuration and cannot grant authority.

The Python runtime rejects another contract set because it has not implemented another combination. A future implementation may support several known profile combinations through an explicit compatibility table, but accepting arbitrary version strings would not make the runtime more portable. It would merely make incompatibility quieter.

### `role-protocols.json` is active authority

Unlike the contract-set manifest, `config/role-protocols.json` participates directly in proposal authorization. `product_write_power` resolves to concrete policy path envelopes. Mutating that declaration changes proposal-gate behavior, and non-proposal roles are forbidden from acquiring product-write power.

`effect_power` is `none` for every reasoning role. Effects remain controller-owned.

### `authority-model.json` is a product authority manifest

`.agent-control/authority-model.json` declares classification, enforcement mode, and mutation owner for the product authority surface. Its entries are validated structurally plus against minimum core invariants rather than by comparing the entire document to one Python tuple table.

Runtime loading checks that machine-enforced artifacts are actually consumed and that product-owned authority files reside within protected authority paths. `release-state.json` is the only controller-mutated authority artifact in this reference.

These three files therefore have deliberately different semantics: compatibility manifest, active role authority, and product authority manifest. Treating all three as interchangeable “configuration” would erase precisely the boundaries v7 is meant to demonstrate.

### External CLI observation extension

Core 1.1.0 implements `verification-evidence/v1` independently of the property-probe transport. Run a controller-authored JSON suite outside a trusted local fixture process:

```bash
./scripts/agentctl verify-cli --workspace /path/to/fixture --suite /path/to/owner-suite.json --trusted-fixture
```

Each case has `id`, `argv`, `predicates`; predicates contain `id`, `op`, `expected` and (for `json_equals`) `pointer`. Supported ops are `exit_code`, `stdout_equals`, `stdout_contains`, `json_equals`. The parent evaluates actual exit/stdout; a candidate-written receipt has no authority. `tests/test_external_cli_profile.py` runs real processes, including wrong output and forged receipt cases. Flow's adapter adds rootless containers, input fixtures, output artifacts and a pinned owner suite.

This is a separately runnable extension, not an arbitrary `contract-set.json` override. The full engine retains its configured property-probe profile. Process observation expectations stay outside the CLI process, but the local fixture executor shares the host and is explicitly for trusted fixtures.

## evidence

V7 adds core control evidence to the existing verification evidence: `goal-evaluation.json`, `control-loop.json`, role protocol artifacts, human decisions, feedback artifacts, merge intent, and per-cycle release transitions. `release-transition-cN.json` binds a verified code merge to controller-owned release-state Git state. Role statements explain reasoning; they do not prove execution.

## security

V7 separates core autonomy from verification security. the runtime profile (see the [generated table](../README.md#contracts)) is **not a security sandbox**. JUnit is not authoritative. The property-probe parent receipt is authoritative only inside deterministic fixture scope. Current final-receipt injection is blocked; raw-outcome forgery remains executable KNOWN-LIMIT. The event chain is **not an authenticity mechanism** without an external anchor. Production hostile code requires stronger isolated verification.

## limitations

The reference is not a production autonomous-engineering runtime. Same-host candidate execution is not a security sandbox; `raw-outcome-forgery` remains executable KNOWN-LIMIT. Generated invariants are finite tests. Deterministic roles prove controller mechanics, not model intelligence. The two-item roadmap demonstrates dependency/reconciliation mechanics, not realistic project-planning scale. Human identity is fixture-only. Local Git adapters do not prove remote provider permissions or deployment semantics.
