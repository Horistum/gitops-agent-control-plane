# Release and versioning policy

This repository versions two different things:

1. repository release tags (`vMAJOR.MINOR.PATCH`);
2. the portable reference contract.

The current contract is:

```text
gitops-agent-control-plane/v4
```

Contract v4 is a breaking refinement of v3 because the authoritative verification model changed: candidate-process JUnit is diagnostic only, product-authored controller probes and baseline negative controls become the acceptance path, process execution semantics were tightened, and schema validation now fails closed on unsupported keywords.

## Repository releases

Public Git tags use Semantic Versioning:

```text
vMAJOR.MINOR.PATCH
```

Before `v1.0.0`, releases are explicitly pre-stable and breaking changes must still be documented.

The intended first public release remains `v0.1.0`, only after clean-room publication validation.

## Contract vs release version

A repository PATCH or MINOR release does not automatically change the contract. The contract version changes when a previously conformant implementation needs semantic changes to remain conformant.

## Schema revisions

Schemas use their instance `schema` fields for document revision. Contract v4 adds scenario, controller-probe and post-merge evidence schemas and makes the built-in schema validator reject unsupported keywords instead of silently ignoring them.

Schema `$id` is intentionally omitted until a stable public resolution namespace is selected. There is no placeholder `$id` validation branch pretending an identifier already exists.

## Release gate

A public tag requires on the exact release commit:

1. `./scripts/agentctl validate` passes;
2. all documented conformance scenarios pass;
3. the Python 3.11/3.12/3.13 CI matrix is green;
4. evidence-forgery scenarios remain blocked by controller probes;
5. publication/security/support files are present;
6. clean-room validation passes;
7. history and release artifacts are reviewed for secrets/private implementation details;
8. release notes list behavioral/schema/security changes;
9. breaking changes include migration guidance.

## Release notes

Each release should name repository version, reference-contract version, schema revisions, conformance changes, security-relevant changes, breaking changes/migrations and known limitations.

## Support window

Until `v1.0.0`, support targets current `main` and the latest public release on a best-effort basis. Backports are not promised.
