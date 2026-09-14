# Release and versioning policy

This repository versions two different things:

1. repository release tags (`vMAJOR.MINOR.PATCH`);
2. the portable reference contract.

The current contract after the hardening review is:

```text
gitops-agent-control-plane/v3
```

The contract moved from v2 to v3 because actor-specific write domains, structured forbidden paths, durable phase semantics, review evidence, schema coverage and recovery behavior changed incompatibly.

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

Schemas use their instance `schema` field for document revision. The v3 hardening adds schemas for policy decisions, reviews, candidate/merge/test/risk/recovery evidence and events.

Schema `$id` is intentionally omitted until a stable public resolution namespace is selected. Placeholder identifiers such as `example.invalid` are forbidden by repository validation.

## Release gate

A public tag requires on the exact release commit:

1. `./scripts/agentctl validate` passes;
2. all documented conformance scenarios pass;
3. the Python 3.11/3.12/3.13 CI matrix is green;
4. publication/security/support files are present;
5. clean-room validation passes;
6. history and release artifacts are reviewed for secrets/private implementation details;
7. release notes list behavioral/schema/security changes;
8. breaking changes include migration guidance.

## Release notes

Each release should name:

- repository version;
- reference contract version;
- schema revisions;
- conformance scenario changes;
- security-relevant changes;
- breaking changes and migrations;
- known limitations.

## Support window

Until `v1.0.0`, support targets current `main` and the latest public release on a best-effort basis. Backports are not promised.
