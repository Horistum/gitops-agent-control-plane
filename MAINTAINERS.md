# Maintainers and decision ownership

The project is stewarded through the Horistum GitHub organization. The current
repository maintainer is [@milank78git](https://github.com/milank78git).
This identifies a project contact, not an assertion of incorporation, trademark
registration, or ownership of every contributor's copyright.

## Contact and responsibilities

Use repository Issues for reproducible bugs, documentation defects, contribution
questions, and non-confidential branding-permission requests. The issue forms
provide the relevant routes. For vulnerabilities or confidential evidence, use
the private route in [.github/SECURITY.md](.github/SECURITY.md); never attach it to
a normal issue or pull request.

Maintainers review changes and release evidence, coordinate security reports,
and route trademark requests to the relevant rights holder. A repository admin
role alone is not proof of authority to license third-party material or a mark.
Before authorizing branding use, identify the actual rights holder and record
that person's or entity's explicit authorization privately.

## Review and release authority

Changes go through pull requests and the required CI checks. `CODEOWNERS` routes
review requests; its presence alone does not make review mandatory on GitHub.
The initial administrator baseline supports a sole maintainer with a required PR
and zero mandatory independent approvals. It must not be described as independent
human review. When a second eligible maintainer is available, raise the required
approval count and enable code-owner approval without permitting self-approval.
Existing stricter review requirements must not be weakened during configuration.

Only an explicit maintainer decision may change repository visibility or publish
a release. Source-policy tests and settings tooling do neither. Follow
[publication](docs/PUBLICATION.md), [releases](docs/RELEASES.md), and
[administrator settings](docs/GITHUB-SETTINGS.md).

Keep GitHub 2FA, recovery access, application permissions, notification delivery,
and the list of maintainers reviewed. These account-level controls are not proven
by a committed policy file or by the repository's test suite.
