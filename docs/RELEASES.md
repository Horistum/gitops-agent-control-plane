# Release and versioning policy

This repository versions repository releases (`vMAJOR.MINOR.PATCH`) separately from the portable reference contract.

Current contract:

```text
gitops-agent-control-plane/v6
```

Contract v6 is a breaking refinement of v5 because verifier semantics changed: negative control is case-level, the stale nonce fixture is replaced by an actually executed current-protocol receipt-injection attack, product verification moves to a generic multi-arg/kwargs generator-expression DSL, core safety artifacts receive schema coverage, and the inherited pipe payload is written only after its reader starts.

## Repository releases

Public tags use Semantic Versioning. Before `v1.0.0`, releases are pre-stable but breaking changes must still be documented. The intended first public release remains `v0.1.0` after clean-room publication validation.

## Contract vs repository version

A repository PATCH/MINOR release does not automatically change the contract. The contract changes when a previously conformant implementation needs semantic changes to remain conformant.

## Release gate

A public tag requires on the exact release commit:

1. `./scripts/agentctl validate` passes;
2. all discovered conformance scenarios reach documented outcomes;
3. Python 3.11/3.12/3.13 CI is green;
4. current receipt-injection and probe-overfitting attacks execute and remain blocked;
5. every generated acceptance negative-control case is rejected on baseline;
6. core authority/effect/human-gate evidence is schema-validated;
7. publication/security/support files are present;
8. clean-room validation and history/secrets review pass;
9. release notes document behavior, schema, security and migration changes.

## Schema revisions

V6 expands schema coverage to authority snapshots, protected-test snapshots, requests, proposals, merge intent, human decisions, roles and fault-injection evidence. Probe-definition and per-case receipt schemas are also stronger. The built-in Draft 2020-12 subset remains explicit and fail-closed on unsupported keywords.

Schema `$id` remains intentionally omitted until a stable public resolution namespace is chosen.

## Support window

Until `v1.0.0`, support targets current `main` and the latest public release on a best-effort basis. Backports are not promised.
