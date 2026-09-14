# Release and versioning policy

This repository versions two different things on purpose:

1. the **repository release**, which tells users which published snapshot they are running;
2. the **reference contract**, which describes compatibility of the portable Goal / Policy / Plan / State / Evidence model.

They are related, but they are not the same version number.

## Repository releases

Public repository releases use [Semantic Versioning](https://semver.org/) in Git tags:

```text
vMAJOR.MINOR.PATCH
```

Examples:

```text
v0.1.0
v0.2.0
v1.0.0
v1.0.1
```

No public release tag should be created merely because a branch is green. A release is a publication event and must satisfy the release gate below.

### Before 1.0

`0.x` releases are explicitly pre-stable. The reference should still document breaking changes, but adopters must expect the architecture, schemas and examples to evolve while the public contract is being refined.

The intended first public release is **v0.1.0**, created only after publication clean-room validation succeeds.

### 1.0 and later

After `v1.0.0`:

- **PATCH**: backward-compatible fixes, documentation corrections and conformance hardening that do not change portable semantics;
- **MINOR**: backward-compatible capabilities, optional schema fields or new scenarios that preserve existing conformant behavior;
- **MAJOR**: incompatible portable-contract or required-behavior changes.

## Reference contract version

The portable compatibility identifier currently used by the reference is:

```text
gitops-agent-control-plane/v2
```

The contract version changes only when implementations that conformed to the previous contract can no longer conform without semantic changes.

A repository release may therefore move from `v0.1.0` to `v0.1.1` or `v0.2.0` while the portable contract remains `gitops-agent-control-plane/v2`.

That separation is intentional. Editing documentation should not manufacture a protocol version, and fixing a test should not imply that every compatible implementation needs a migration.

## Schema revisions

The JSON documents under `schemas/` carry their own `schema` revision in data instances.

Rules:

- compatible clarifications may keep the same schema revision;
- adding an optional field may remain compatible if old consumers can safely ignore it and conformance semantics are unchanged;
- removing, renaming or changing the meaning/type of a required field requires a new schema revision;
- if a schema change also alters portable behavioral guarantees, increment the reference contract major as well.

Schema `$id` values must be stable before the first public release. Placeholder identifiers are a release blocker, not something to quietly fossilize into `v1.0.0` because changing them later is annoying.

## Release gate

A public tag/release requires all of the following on the exact release commit:

1. `./scripts/agentctl validate` passes;
2. `./scripts/agentctl conformance` passes all documented scenarios;
3. GitHub `Reference integrity` is green on the exact commit;
4. `LICENSE`, `NOTICE`, `TRADEMARKS.md`, `CONTRIBUTING.md`, `.github/SECURITY.md` and `SUPPORT.md` are present and consistent;
5. the clean-room test defined in `docs/PUBLICATION.md` has passed for the release candidate;
6. repository history/release artifacts have been checked for secrets and unintended private implementation details;
7. release notes list meaningful behavioral, schema and compatibility changes;
8. any breaking change includes a migration note.

## Release notes

Each GitHub Release should summarize:

- reference contract version;
- schema revisions changed;
- added/changed conformance scenarios;
- security-relevant changes;
- breaking changes and migration guidance;
- known limitations.

Release notes must not claim capabilities that are not demonstrated by the standalone reference or its conformance suite.

## Support window

Until `v1.0.0`, the project supports the current `main` branch and the latest public release on a best-effort basis. Backports are not promised.

After `v1.0.0`, the exact maintenance window may be tightened, but any change to support policy must be recorded in `SUPPORT.md` before the release that relies on it.
