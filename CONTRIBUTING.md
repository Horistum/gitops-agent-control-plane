# Contributing

Contributions are welcome when they preserve provider-neutral, bounded software
delivery through Git. Keep one shared authority and evidence contract, with a
clear boundary between proposals, owner policy, execution, and observed results.

## Development and review

Use Linux or WSL and Python 3.11 or later. The CI verification matrix covers
Python 3.11, 3.12, and 3.13. Use a topic branch and a pull request rather than
pushing directly to the default branch. Explain the problem and scope, add
regression tests for changed behavior and fail-closed cases, and run:

```bash
./scripts/agentctl validate
python3 scripts/check_publication.py
```

For distribution changes, also run the package round-trip described in
[RELEASES](docs/RELEASES.md). Actual rootless Podman execution is a separate CI
job; fixture tests do not replace it. Never use live model credentials for an
untrusted contribution's CI run.

Code, comments, error messages, and project documentation must be in English.
Unicode fixtures may intentionally contain other languages to test behavior.
Do not rename existing public APIs, CLI verbs, import paths, wire identities or
consumer lock formats as part of a branding or documentation change.

Do not commit local credentials, authority files, run state, private source,
customer data, or private consumer deployment records. Do not attach those data
to an issue, PR, or CI artifact. See [provenance](docs/PROVENANCE.md).

## Licensing of contributions

Unless explicitly stated otherwise, contributions intentionally submitted for
inclusion are provided under Apache License 2.0, consistent with Section 5.
A submission marked otherwise must not be merged until its terms are resolved.
This project does not currently require a separate Contributor License Agreement.

Submit only material you are entitled to contribute. Identify third-party
provenance and applicable licenses, including notices that must be retained.
Check employer or client restrictions before contributing their material.
AI-assisted contributions require the same provenance and review care; generated
content is not automatically free of third-party rights.

Retain `LICENSE`, `NOTICE`, and relevant attribution. Names and branding remain
separate from the software license; see [TRADEMARKS.md](TRADEMARKS.md).

## Reporting and conduct

Use issue forms for bugs and concrete feature proposals. Report vulnerabilities
privately following [.github/SECURITY.md](.github/SECURITY.md). Be respectful,
focus criticism on work rather than people, and avoid disclosing personal or
confidential information. Maintainers may moderate abuse or off-topic material.
Support scope is defined in [SUPPORT.md](SUPPORT.md), not implied by a license.
