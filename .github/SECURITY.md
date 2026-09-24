# Security policy

**Do not open a public GitHub issue for a suspected vulnerability.** Do not attach
credentials, private source, or raw run receipts to issues or pull requests.

## Private reporting

The intended public reporting route is **GitHub Private Vulnerability Reporting**:
open the repository's Security tab, select Advisories, then Report a vulnerability.
Maintainers must enable this route as part of the controlled public transition
and test receipt of a benign report and notifications from an external account
before announcing the project. Availability is not established by this file.

GitHub provides this feature for public repositories. While the repository is
private, use an existing private maintainer/organization channel. An anonymous
public clone and external vulnerability-report test belong after the visibility
transition, not before it. See [publication](../docs/PUBLICATION.md).

If the reporting action is unavailable, do not disclose vulnerability details.
Request a private contact route from a [maintainer](../MAINTAINERS.md), using only
a non-sensitive contact request. Do not infer that an unlisted email address is
monitored. A usable private route and notification delivery are launch gates.

## Security-sensitive reports

Report authority or approval bypass, path traversal or workspace escape, forged
or wrong-revision evidence, unsafe replay/duplicate effects, credential exposure,
and supply-chain issues that violate the documented trust model. Identify the
profile and whether the issue applies to actual operational execution or only
to a documented deterministic fixture limitation.

Include the affected version/commit, minimal reproduction with synthetic data,
expected boundary, observed result, and impact. Avoid live secrets and unrelated
private information. Documented limits do not prevent reporting a new impact or
a bypass outside the stated scope.

## Disclosure and supported versions

Security handling is best-effort; there is no contractual response-time SLA.
Maintainers aim to acknowledge, investigate, and coordinate remediation privately
before disclosure. Credit and advisories should accurately describe the affected
profile and avoid making claims about unrelated deployments.

Before a public release, fixes target current `main`. After releases begin,
maintainers support `main` and the latest public release; older backports are not
guaranteed. See [support](../SUPPORT.md) and [releases](../docs/RELEASES.md).
