# Support policy

This project is maintained on a **best-effort basis**. There is no response-time
guarantee, contractual security-response SLA, availability commitment, or
commercial support agreement attached to an open-source license.

## Supported scope

Within maintainer capacity, support covers the pure `control_plane_core`, the
owner-operated `agent_runtime`, its bundled command adapters, published schemas,
installation, and the documented deterministic `reference_runtime` scenarios.
The supported runtime deployment is single-host Linux or WSL, with local durable
state and one writer per run. CI verifies Python 3.11, 3.12, and 3.13; the declared
Python minimum is 3.11. Newer Python versions are not automatically CI-certified.

Report reproducible repository bugs and documentation defects through GitHub
Issues. Focused pull requests should follow [CONTRIBUTING.md](CONTRIBUTING.md).
Use the private reporting route in [.github/SECURITY.md](.github/SECURITY.md) for
suspected vulnerabilities, not a public issue.

## Version support

Before the first public tagged release, fixes target current `main`. Once public
releases exist, fixes target `main` and the latest public release. There is no
promise to backport to older releases. A fix may require upgrading to the next
patch, minor, or major release as appropriate; breaking changes are identified.
Pre-releases are evaluation builds and carry no separate maintenance window.
This policy applies after 1.0 as well as before it. See [RELEASES](docs/RELEASES.md).

A version in source metadata is not proof of a published tag or registry upload.
Pin a reviewed release or exact commit instead of treating a moving branch as a
repeatable dependency.

## Outside support

No guarantee is made for private consumer products, unrestricted third-party
agent sessions, custom forks, provider account quota/billing, organizational
identity or network design, shared multi-tenant hosting, or production deployment
of a user's own platform. Consumer activation, policies, verification commands,
credentials, build images, and host security remain consumer responsibilities.

## Useful bug reports

Provide the exact release or commit, OS and Python versions, command, expected
and actual results, and a minimal reproduction. State whether the case uses the
operational runtime or deterministic fixtures. Include only redacted, relevant
logs; run directories and receipts may contain private source and proposals.
Do not upload a whole state directory or credential file.

A delayed response does not imply acceptance, certification, endorsement, or a
future product commitment. Any commercial support would require separate terms.
