# Release and versioning policy

This repository versions two different things:

1. repository release tags (`vMAJOR.MINOR.PATCH`);
2. the portable reference contract.

The current contract is:

```text
gitops-agent-control-plane/v5
```

Contract v5 is a breaking refinement of v4 because the verifier trust/oracle model changed: receipt secrets move out of argv into a private inherited control FD, a trusted verifier parent no longer imports candidate code, final receipts are HMAC-authenticated and singular, candidate children receive only current generated inputs, and verification definitions use runtime-generated cases plus invariants instead of public fixed tuples.

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

Schemas use their instance `schema` fields for document revision. Contract v5 revises policy/probe evidence contracts and adds a schema for generated verification definitions. The built-in schema validator continues to reject unsupported keywords instead of silently ignoring them.

Schema `$id` is intentionally omitted until a stable public resolution namespace is selected.

## Release gate

A public tag requires on the exact release commit:

1. `./scripts/agentctl validate` passes;
2. all documented conformance scenarios pass;
3. the Python 3.11/3.12/3.13 CI matrix is green;
4. evidence-forgery and probe-overfitting scenarios remain blocked by signed randomized controller probes;
5. verifier secrets are absent from candidate argv/environment and probe definitions are absent from the candidate workspace;
6. publication/security/support files are present;
7. clean-room validation passes;
8. history and release artifacts are reviewed for secrets/private implementation details;
9. release notes list behavioral/schema/security changes;
10. breaking changes include migration guidance.

## Release notes

Each release should name repository version, reference-contract version, schema revisions, conformance changes, security-relevant changes, breaking changes/migrations and known limitations.

## Support window

Until `v1.0.0`, support targets current `main` and the latest public release on a best-effort basis. Backports are not promised.
