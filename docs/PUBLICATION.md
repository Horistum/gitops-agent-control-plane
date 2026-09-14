# Publication readiness

The reference is intentionally standalone, implementation-neutral and free of private runtime or product dependencies.

## Licensing and provenance

The publication model is now defined:

- repository source code, documentation, schemas and examples are licensed under **Apache License 2.0**;
- `LICENSE` contains the full Apache-2.0 license text;
- `NOTICE` records the project's Horistum provenance and canonical repository;
- `TRADEMARKS.md` keeps the Horistum name and branding separate from the software license;
- `CONTRIBUTING.md` states that normal contributions are submitted under Apache-2.0 unless explicitly stated otherwise.

The intended result is low-friction adoption: users may study, fork, modify, redistribute and use the reference commercially under Apache-2.0 while preserving the attribution required by the license and `NOTICE`.

## Horistum positioning

This repository should present Horistum as the **origin and steward of the reference architecture**, not as a claim that this repository is the source distribution of a commercial Horistum product.

Preferred wording:

> Initiated and maintained by the Horistum project.

and:

> This reference architecture was originally developed and published from the Horistum GitHub organization.

Avoid introducing private product names, private repositories, unreleased runtime details or marketing claims that cannot be demonstrated by the standalone reference.

A future Horistum product may cite this repository as an open reference demonstrating the underlying architectural principles. The reference should remain useful on its own and should not become product documentation by stealth.

## Trademark boundary

Apache-2.0 licenses the copyrightable work, not the Horistum brand. Factual statements about origin are welcome and expected. Forks and derivatives should use their own names and branding and must not imply official Horistum status, certification, endorsement or partnership without separate permission.

See `TRADEMARKS.md` for the repository policy.

## Remaining publication gates

Before changing repository visibility to public, complete these remaining items:

1. define a private security-reporting path, preferably GitHub Private Vulnerability Reporting or a dedicated security address;
2. define release/versioning policy for the reference contract and schemas;
3. state public support expectations clearly, including whether support is best-effort/community-only;
4. run a clean-room publication test from an account and machine with no Horistum organization access;
5. confirm that no Git history or release artifact exposes secrets or private implementation details intended to remain private.

## Clean-room acceptance test

From a new account/environment, clone the repository using only public access and run:

```bash
./scripts/agentctl bootstrap check
./scripts/agentctl validate
./scripts/agentctl demo all
```

Acceptance criteria:

- no organization-specific credentials are required;
- no private repository or package is referenced;
- all five conformance scenarios produce their documented terminal states;
- `LICENSE`, `NOTICE`, `TRADEMARKS.md` and `CONTRIBUTING.md` are present;
- README provenance remains accurate without exposing private product information.

## Publication principle

The repository should make the architectural idea easy to inspect, execute and reuse while keeping authorship/provenance visible. The strongest long-term Horistum positioning is not to make the reference artificially restrictive; it is to publish a useful reference early, preserve its documented origin, maintain it well, and later show how production Horistum capabilities extend beyond the reference implementation.
