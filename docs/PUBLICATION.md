# Publication readiness

A passing source or CI check is not authorization to make this repository public.
The process separates private preparation, the controlled visibility transition,
and public launch. Only the maintainer can authorize the transition. No supplied
script changes visibility, publishes a tag/release, or claims legal clearance.

## 1. Private preparation

Select the exact candidate commit and record all checks against it. Complete:

1. Review provenance and the intended public boundary using [PROVENANCE](PROVENANCE.md).
   Identify the rights holder for branding decisions; do not invent registration.
2. Inspect all retained Git refs/history, commit messages, PR/issue discussions and
   attachments, Actions logs/caches/artifacts, and release assets for secrets and
   private implementation details. Run the redacted history scanner and triage
   its findings. A full-history scan is still only its fetched-ref scope. Deleted
   or unmerged PR refs and non-Git data require a separate review. Rotate any real
   exposed credential before considering content removal.
3. Run the source, test, package, and container checks below. Test a clean snapshot
   with no organization credentials. This is a clean-room snapshot test, not an
   anonymous public clone of a private repository.
4. Audit and prepare [GitHub settings](GITHUB-SETTINGS.md), administrator 2FA,
   application permissions, recovery access, and notification ownership. Enable
   all supported protections while private. Record plan-limited or inaccessible
   features as blocked/unknown, never as successful.
5. Verify that required license and NOTICE bytes are present in both the wheel and
   source archive. Review new dependencies and the final public README.
6. Keep an exact-commit decision record naming reviewer, timestamp, evidence
   locations, known limits, outstanding gates, and explicit visibility approval.
   Store confidential audit records outside the public source tree.

Source checks:

```bash
./scripts/agentctl bootstrap check
./scripts/agentctl validate
python3 scripts/check_publication.py
python3 scripts/check_distribution.py --output /absolute/private-audit/package-check
python3 scripts/github_settings.py audit --output /absolute/private-audit/github-settings.json
```

`validate` discovers the complete unit suite and all documented conformance
scenarios from `examples/scenarios/`; publication checks must not rely on a stale
hard-coded count. The separately available `./scripts/agentctl conformance`
repeats those scenarios. Every scenario must reach its documented outcome,
including the explicit `raw-outcome-forgery` known limit, on the supported CI
matrix. Operational tests with controlled peers do not prove live model quality.

The package checker needs the declared setuptools build backend installed; see
[RELEASES](RELEASES.md). The history workflow runs Gitleaks over a non-shallow
checkout, emits redacted findings and records the fetched refs. A green result
does not cover issue text, attachments, or every historical workflow run.

## 2. Controlled visibility transition

Only after the private gates and explicit owner authorization:

1. An administrator changes visibility in GitHub. This is intentionally manual;
   public copies/forks cannot be recalled by switching the repository back.
2. Immediately enable/verify protection of `main`, its strict required CI checks,
   and private vulnerability reporting. A private-repository plan limitation may
   require this step immediately after transition. Do not advertise the project
   or accept ordinary contributions until these controls are verified.
3. Enable available Secret Scanning, Push Protection and Dependabot alerts, review
   their results, and verify organization/Actions policies. Configure code
   scanning where supported; do not equate a committed workflow with activation.

GitHub Private Vulnerability Reporting and an anonymous public clone can only be
externally verified after the repository becomes public. They must not be used
as circular prerequisites for the private preparation phase.

## 3. Public validation before announcement

Use an account outside Horistum and a clean environment without organization
access. Perform an actual public clone of the exact selected commit, repeat the
validation and package checks, and verify that no private dependency is needed.
Submit a clearly marked benign private vulnerability report and confirm both
maintainer receipt and notifications, then close the test report. Check that bug
and feature issue forms are available and route security reports privately.

Review the now-public repository view and artifacts for accidental disclosures.
Record these external observations and the active branch/security settings. Only
then announce the project and issue the tested version under [RELEASES](RELEASES.md).

## Evidence boundaries

`check_publication.py` validates repository files only. `github_settings.py audit`
reads the settings available to its credential; HTTP 403/404 is not a substitute
for a successful read. Build and history reports describe exact inputs and tool
scope. None of these establishes trademark ownership, human review, account 2FA,
a live model turn, a deployed consumer, or public launch approval.

The reference is maintained by Horistum but is independently usable. Consumer
source locks, deployments and private operational instructions belong to the
consumer, not to the public reference's release claims.
