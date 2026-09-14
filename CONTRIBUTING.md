# Contributing

Contributions are welcome when they preserve the reference project's purpose: a small, executable and implementation-neutral demonstration of bounded autonomous software delivery through Git.

## Before opening a change

Please keep changes focused and preserve the distinction between:

- product-authored authority;
- reasoning/proposals;
- controller-owned execution;
- independently verifiable evidence.

A new feature should normally include executable verification or a conformance scenario showing both the allowed behavior and relevant fail-closed behavior.

## Validation

Before submitting a pull request, run:

```bash
./scripts/agentctl validate
./scripts/agentctl conformance
```

## Licensing of contributions

Unless you explicitly state otherwise, contributions intentionally submitted for inclusion in this repository are provided under the Apache License 2.0, consistent with Section 5 of that license.

If material is not your original work, make its provenance and licensing explicit. Do not submit third-party code, documentation or assets whose terms are incompatible with Apache-2.0.

This project does not currently require a separate Contributor License Agreement.

## Attribution and naming

Do not remove `LICENSE`, `NOTICE`, or relevant attribution notices. The Horistum name and branding are not licensed as part of the source code; see `TRADEMARKS.md`.

Forks and derivatives are welcome, but modified distributions should use distinct branding and must not imply that they are official Horistum releases.
