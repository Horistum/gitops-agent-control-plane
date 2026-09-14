# Support Policy

The GitOps Agent Control Plane Reference is an open technical reference maintained by the Horistum project on a **best-effort, community-oriented basis**.

It is not a commercial support offering and does not carry an availability, response-time, maintenance or compatibility SLA.

## What maintainers intend to support

Within available capacity, maintainers may help with:

- reproducible bugs in the standalone reference runtime;
- failures in the documented conformance scenarios;
- inconsistencies between schemas, documentation and executable behavior;
- portability-contract questions grounded in this repository;
- documentation corrections;
- focused proposals that improve the reference without turning it into a product-specific implementation.

## What is outside repository support

This repository does not promise support for:

- production deployment of a user's own autonomous engineering platform;
- private or unreleased Horistum products;
- custom model-provider integrations;
- organization-specific CI/CD, identity, network or compliance architecture;
- custom forks whose behavior differs materially from the reference;
- general Git/GitHub/Python/Linux administration;
- guaranteed architecture consulting or migration assistance;
- backports to every historical release.

People are free to build those things with the reference, but an Apache-2.0 license is not a magical support contract. Humanity has tried this misunderstanding often enough already.

## Where to ask for help

After public launch:

- use **GitHub Issues** for reproducible reference bugs and concrete documentation defects;
- use pull requests for focused fixes that satisfy `CONTRIBUTING.md`;
- use the normal issue workflow for feature proposals, including the problem, expected invariant and how the proposal can be tested.

Do **not** use public issues for security vulnerabilities. Follow `.github/SECURITY.md` and use GitHub Private Vulnerability Reporting.

## Good bug reports

Please include:

- repository release/tag or commit SHA;
- operating system and Python/Git versions when relevant;
- exact command used;
- expected result;
- actual result;
- minimal reproduction;
- relevant evidence from `.demo/runs/.../evidence/` with secrets/private data removed.

A reproducible failing conformance scenario is particularly useful.

## Compatibility and versions

Versioning and release support are defined in `docs/RELEASES.md`.

Before `v1.0.0`, support is focused on current `main` and the latest public release. Backports are best-effort and not guaranteed.

A newer `main` branch may contain unreleased behavior. Consumers that need repeatability should use a tagged release once public releases exist.

## Response expectations

Issues and pull requests are triaged as maintainer capacity permits. No response-time guarantee is made.

Lack of an immediate response does not imply acceptance, rejection, certification or future product commitment.

## Relationship to Horistum

Horistum is the origin and steward of this reference architecture, as documented in `NOTICE` and the README.

Support for this open reference must remain distinct from any future commercial Horistum product or service. If commercial support is offered in the future, its terms will be published separately rather than silently attaching enterprise expectations to this repository.
