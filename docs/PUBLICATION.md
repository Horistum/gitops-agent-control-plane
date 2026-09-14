# Publication readiness

The reference is intentionally standalone, implementation-neutral and free of private runtime or product dependencies.

## Licensing and provenance

The publication model is defined:

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

## Publication controls now defined

The first three operational publication policies are now explicit.

### 1. Private security reporting

`.github/SECURITY.md` defines **GitHub Private Vulnerability Reporting** as the canonical public security-reporting channel.

Security vulnerabilities must not be reported through public Issues. Before repository visibility is changed to public, maintainers must enable Private Vulnerability Reporting in GitHub repository settings and verify that **Report a vulnerability** works from an account outside the Horistum organization.

The policy intentionally does not invent an unattended `security@...` address merely to satisfy a checklist.

### 2. Release and versioning policy

`docs/RELEASES.md` defines:

- repository releases using Semantic Versioning tags `vMAJOR.MINOR.PATCH`;
- a separate portable reference-contract version (`gitops-agent-control-plane/v2`);
- schema revision rules;
- release notes requirements;
- the exact release gate;
- `v0.1.0` as the intended first public release after clean-room validation.

No public tag should be created before the release gate is satisfied.

### 3. Public support expectations

`SUPPORT.md` defines the repository as **best-effort/community-oriented** support with no SLA.

It also separates support for this open reference from any future commercial Horistum product or service. GitHub Issues may be used for reproducible reference bugs and concrete proposals after public launch; security findings follow `.github/SECURITY.md` instead.

## Remaining publication gates

Before changing repository visibility to public, complete the remaining operational checks:

1. enable GitHub Private Vulnerability Reporting and verify the external reporting flow;
2. run the clean-room publication test from an account and machine with no Horistum organization access;
3. confirm that no Git history or release artifact exposes secrets or private implementation details intended to remain private;
4. replace any placeholder schema identifiers that should become stable public identifiers before the first tagged release.

These are operational verification gates. The policy decisions for licensing, security reporting, versioning and support are already defined.

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
- `LICENSE`, `NOTICE`, `TRADEMARKS.md`, `CONTRIBUTING.md`, `.github/SECURITY.md` and `SUPPORT.md` are present;
- README provenance remains accurate without exposing private product information;
- the private vulnerability-reporting path is available to an external reporter.

## First public release

After all remaining publication gates pass, the intended sequence is:

1. make the repository public;
2. repeat the clean-room test using only public access;
3. create the first tagged release `v0.1.0` from the exact tested commit;
4. publish release notes according to `docs/RELEASES.md`.

This keeps public visibility and release identity tied to evidence rather than to the optimistic assumption that changing a GitHub toggle counts as a release process.

## Publication principle

The repository should make the architectural idea easy to inspect, execute and reuse while keeping authorship/provenance visible. The strongest long-term Horistum positioning is not to make the reference artificially restrictive; it is to publish a useful reference early, preserve its documented origin, maintain it well, and later show how production Horistum capabilities extend beyond the reference implementation.
