# Security Policy

Security reports for this repository must be handled privately.

## Reporting a vulnerability

**Do not open a public GitHub issue for a suspected vulnerability.**

The canonical public-reporting path for this project is **GitHub Private Vulnerability Reporting** through the repository **Security** tab and **Report a vulnerability** action.

Before this repository is made public, maintainers must enable GitHub Private Vulnerability Reporting. Public visibility is a hard publication gate until that private reporting path is confirmed to work from an account outside the Horistum organization.

While the repository remains private and in publication preparation, security findings should be shared only with Horistum organization maintainers through an existing private organizational channel. Do not create a public disclosure path merely to make the checklist look complete.

## What should be reported as security-sensitive

Examples include:

- bypasses of product-authority or write-boundary enforcement;
- path traversal, symlink, workspace-escape or arbitrary-file-write behavior;
- evidence spoofing or acceptance of evidence bound to the wrong Git identity;
- replay or duplicate-effect behavior after crash recovery;
- ways to bypass a required human decision or risk gate;
- integrity failures in the hash-linked event/evidence model;
- secret or credential exposure in repository content, history, CI logs or release artifacts;
- supply-chain issues in release automation or required GitHub Actions;
- vulnerabilities in the standalone reference runtime that materially violate the documented security model.

Normal correctness bugs, documentation issues and feature proposals are not security reports and should use the normal repository issue workflow after public launch.

## What to include

A useful report should contain, when possible:

- affected commit or release;
- affected file/component;
- minimal reproduction steps;
- observed behavior and expected security boundary;
- impact assessment;
- whether the issue is known to be exploitable outside the reference/demo environment;
- any suggested mitigation.

Please avoid including real credentials, tokens or unrelated private data in a report.

## Disclosure and response expectations

This is an open reference project maintained on a **best-effort basis**. There is no contractual security-response SLA.

Maintainers will aim to acknowledge, triage and coordinate remediation privately before public disclosure when the report is valid. Reporters are asked to avoid public disclosure until a fix or reasonable mitigation has been prepared, unless immediate disclosure is required to protect users.

Security advisories and credit should describe the reference project accurately and should not imply that this repository is a production Horistum product.

## Supported versions

Until the first public tagged release, only the current `main` branch is considered for security fixes.

After public releases begin, the support window follows `docs/RELEASES.md` and `SUPPORT.md`.
