# Verification, evidence and trust boundaries

## What the evidence establishes

| Layer | What runs | Evidence boundary |
|---|---|---|
| Core conformance | Pure decisions, invalid inputs and full phase graph | Semantics for supplied observations |
| Operational integration | Real Git, processes, test failures/repairs, exact merge and postmerge execution | Reasoning and GitHub HTTP peers are test doubles |
| Rootless execution CI | Actual Podman across baseline, negative control, candidate and merge | Test reasoning peer and finite sample product |
| Installed distribution CI | Two-item lifecycle from installed wheel outside checkout | Package completeness and real local execution |
| Codex CLI contract CI | Actual pinned CLI capabilities and protocol regressions | No authenticated model turn or reasoning-quality claim |
| Deterministic scenarios | Fixture proposals, property probes and injected faults | Reproducible mechanics and explicit known limits |
| Consumer compatibility | Exact clean consumer revision tested with current core | That revision's suite; no deployment or activation |
| Operator installation | Prerequisite checks and authorized live product goal | Requires actual account, image, Git credentials and protected repository |

## Operational acceptance

The controller executes immutable Git snapshots. Commands, image, JUnit selectors,
CLI cases and acceptance types come from owner-held policy and goal snapshots
outside the editable product. Models propose data; they cannot supply a trusted
`passed` boolean or select executable commands.

1. Original baseline tests pass with stable `class:name` identities.
2. Candidate verification preserves those executed identities.
3. An independent tester adds new files and binds exact tests to typed criteria.
4. The same files run on the original base. New-behavior bindings fail by assertion;
   regression bindings pass. Missing identities and harness errors fail the gate.
5. Accepted assertions freeze across repairs/replans, merge verification and later
   items. A model cannot weaken them to repair a product.
6. Documentation requires changed nonempty blobs and role review. CI uses latest
   successful named checks from the declared App on the exact revision. Requested
   integration evidence executes the exact synthetic two-parent merge.
7. Delivery requires exact merge identity, actual postmerge execution, trusted
   postmerge checks when configured, all due obligations and typed machine goal
   conditions. Earlier accepted tests remain regression obligations.

Reviews assess every criterion. Future CI/delivery claims remain deferred.
Candidate approval is not completed delivery. A failed trusted check or ambiguous
harness failure stops progress.

## Security

Rootless Podman receives only a temporary product snapshot. It has no network,
host credentials or receipt/state mounts; its image is pinned and already present.
The root filesystem is read-only, capabilities are dropped, and CPU, memory,
process and time limits apply. Timeout triggers container cleanup. Product code
is never imported into the controller. These controls do not prove protection
against kernel/container-runtime vulnerabilities.

Codex runs in an empty directory with user configuration/rules ignored, ephemeral
structured output, read-only sandbox and effect tools disabled. Product files
arrive as bounded data. Only its authenticated Codex home is provided; API fallback
and product/GitHub credentials are absent. The executable, external provider
wrapper and host remain trusted infrastructure. Unexpected tool events fail the
protocol gate; that gate cannot make a malicious executable safe.

JUnit is **candidate-controlled output**, even in a container. Parsing counts
actual cases and rejects duplicate/missing identities, stale reports, oversized
XML, DTD/entities and report symlinks. Counterfactuals and protected test tooling
expose common fabricated success, but arbitrary candidate code can still fabricate
JUnit. Owner-authored CLI assertions are evaluated in the parent against actual
exit/stdout from fresh snapshots; candidate-written receipts cannot replace them.
Finite tests and outputs do not prove every behavior.

Use independent external cases for important observable behavior. Protect existing
tests, runners and CI configuration. Networked builds need a different explicit
profile; network is not silently enabled. `trusted-local` is for owner-trusted code
and is not a security sandbox.

Receipts bind request, revisions, authority/runtime identity and output digest.
They live in private controller state. Hashes detect accidental mismatch; they
cannot authenticate against an attacker controlling the owner's host. The owner
account authenticates CLI approvals; there is no separate multi-user identity service.

## Deterministic fixture profile

The [generated contract table](../README.md#contracts) names the retained fixture
composition. `config/contract-set.json` is a compatibility manifest;
`config/role-protocols.json` actively grants proposal envelopes;
`.agent-control/authority-model.json` classifies sample product authority.
These have different purposes and are not arbitrary runtime toggles.

This profile uses generated property probes, case-level negative controls, HMAC
parent receipts and promoted acceptance probes. Role proposals, including repairs,
are predeclared fixtures. `raw-outcome-forgery` remains executable **KNOWN-LIMIT**:
same-host hostile code can undermine raw observations. Receipt injection is
blocked within the declared scope. A passing conformance run reproduces this
limit; it does not remove it. The event chain is not an authenticity mechanism
without an external anchor.

`agentctl verify-cli --trusted-fixture` remains a separately runnable local
observation demonstration. The operational runtime integrates shared typed process
predicates directly into candidate and postmerge gates.

## JSON Schema compatibility

Published schemas use a supported subset of JSON Schema Draft 2020-12 and remain
valid standard schemas. The local validator rejects unknown keywords, including
nested unused schemas. It implements boolean/number equality, integer-valued
numbers, numeric uniqueness and substring regex semantics. Published identity
patterns explicitly constrain full strings.

CI compares supported cases and all published schemas with `jsonschema` through
`tests/test_schema_interoperability.py --require-reference`. That dependency is
development-only. Full vocabulary support, arbitrary regex dialects and schema
composition are not promised. New keywords require semantics and differential
tests, or explicit adoption of a full validator. See the
[validation specification](https://json-schema.org/draft/2020-12/json-schema-validation).
