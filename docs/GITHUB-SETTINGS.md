# Repository administration and publication settings

The desired repository identity, metadata, topics and required CI/App bindings
are in [.github/repository-settings.json](../.github/repository-settings.json).
This is desired state, not evidence of settings currently active on GitHub.
The supplied helper is **read-only**: all network requests use GET. It cannot
apply policies, change visibility, read secrets, or publish a tag or release.

## Read-only audit

From a trusted checkout with `gh` installed and authenticated to github.com:

```bash
python3 scripts/github_settings.py audit \
  --output /absolute/private-audit/github-settings.json
```

The report records repository identity, current main SHA, observed HTTP statuses,
and per-control `pass`, `fail`, `unknown` or `deferred` states. Exit 2 means the
observed baseline is not fully verified. Exit 1 indicates invalid input or an
unusable audit. `settings_passed` covers only the reported settings, never legal
clearance, account controls or authorization to publish. No settings are changed.

HTTP 403 is unknown/inaccessible, not disabled. A 404 on branch protection counts
as absence only with a separately observed unprotected branch. A ruleset-only
branch requires manual equivalent verification rather than a false successful
classic-protection result. Effective linear-history rules are reported as a
conflict because the runtime requires two-parent merge commits.

A managed connection may expose repository metadata without Administration
permission. Use your own authorized GitHub session to inspect the missing controls.
Do not put administrator credentials in a PR workflow, this repository, or logs.
Plan-limited features stay pending until the owner changes the plan or performs
the separately authorized public transition. The helper does neither.

## Manual configuration in GitHub

In the repository's About panel, set the description, documentation link and
topics from the desired-state JSON. Preserve any additional relevant topics.
In Settings > General, keep Issues and merge commits enabled. Optional convenience
settings are branch updating and automatic deletion of merged topic branches.
Do not change visibility as part of this configuration cleanup.

In Settings > Branches or Rules > Rulesets, protect `main` with required pull
requests, strict required status checks, resolved review conversations, stale
approval dismissal, no force pushes, no deletion and no administrator bypass.
Bind required check names to GitHub Actions App ID 15368. Use all seven exact
contexts in the desired-state JSON; first confirm each has a successful run.
A committed workflow does not make a check required on the server.

The initial minimum review count is zero to support a sole maintainer. This
still requires a PR and CI, but is **not independent human review**. Raise the
threshold and require code-owner approval when a second eligible reviewer is
available. Never lower existing stronger thresholds, remove extra required
checks, weaken dismissal/push restrictions or disable signature requirements
just to match a minimal baseline. Resolve incompatible trusted-App bindings
explicitly. Keep two-parent merge commits available; do not require linear
history or squash-only merging.

Protect `v*` release tags from updates and deletion with an active no-bypass tag
ruleset named `public-release-tag-integrity`, applying to `refs/tags/v*` without
exclusions. Tag creation and release approval remain separate maintainer actions.
Review existing and inherited rules rather than replacing them blindly.

## Actions and security

In Settings > Actions > General, use read-only default workflow permissions,
disable workflow PR approval, and require approval for external contributors.
Review the organization's action allowlist, fork-token/secret policy, runner
access and artifact retention. Do not broaden an existing allowlist. Use hosted
runners for untrusted PRs and never execute their content with privileged
`pull_request_target` credentials.

The committed workflows pin actions to full SHAs, remove persisted checkout
credentials and bound job execution. Dependabot proposes action/Python updates;
actual alert activation is a separate setting. Enable available Dependabot alerts,
Secret Scanning and Push Protection in the repository's security settings. Do not
purchase or activate paid private-repository features without the owner's decision.
Configure a reviewed code scanner such as CodeQL where supported; its activation
is not certified by the source-policy checks.

At the explicitly authorized public transition, enable Private Vulnerability
Reporting and verify an external benign report plus maintainer notifications
before announcement. Run the audit again after manual changes and review the
read-back report. A private-repository plan restriction is not evidence that the
future public setting has been enabled. See [PUBLICATION](PUBLICATION.md).

## Separate account and rights controls

Review organization 2FA, recovery access, installed applications, least-privilege
permissions and notification ownership in GitHub. Establish provenance and
branding authority following [PROVENANCE](PROVENANCE.md). Neither an admin role
nor this audit establishes copyright ownership or launch authorization.

Official references: [branch protection API](https://docs.github.com/en/rest/branches/branch-protection),
[Actions permissions API](https://docs.github.com/en/rest/actions/permissions),
[GitHub CLI API](https://cli.github.com/manual/gh_api),
[private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository),
and [secure Actions use](https://docs.github.com/en/actions/reference/security/secure-use).
