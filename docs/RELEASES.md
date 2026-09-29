# Release and versioning policy

Current distribution: **1.10.1**.

The distribution version in `pyproject.toml` and `control_plane_core.__version__`
is separate from wire identities authored in
[config/contract-set.json](../config/contract-set.json). Those identities are
projected into the [generated contract table](../README.md#contracts). A profile
change does not automatically change every core/wire contract.

Tags use `vMAJOR.MINOR.PATCH`, exactly matching the tested distribution version.
Do not restart numbering merely because a repository becomes public. A merged
source revision is not a claim that a GitHub release or registry upload exists.

## Compatibility and support

Patch releases fix compatible defects, packaging and documentation. Minor
releases add compatible functionality. Breaking public API, CLI, state or wire
changes require an explicitly documented compatibility decision and appropriate
major version or separately versioned contract. Do not rename technical APIs for
branding. Support covers `main` and the latest public release, with no guaranteed
older backports, as detailed in [SUPPORT](../SUPPORT.md).

Consumer source pins and installed runtimes do not update automatically. Review
and run that consumer's own acceptance/activation gates before adopting new core
bytes. Runtime upgrades still require the documented quiescent boundary.

## Build and inspect the actual distribution

Use a disposable build environment with Python 3.11+ and the declared setuptools
backend (77 or later). No build-time dependency is installed by the runtime.

```bash
python3 -m venv /absolute/build-env
/absolute/build-env/bin/python -m pip install 'setuptools>=77'
/absolute/build-env/bin/python scripts/check_distribution.py   --output /absolute/private-audit/package-check
```

The checker builds a source archive with the backend declared in `pyproject.toml`,
safely extracts it in a clean temporary directory, and builds a wheel from those
extracted bytes. It validates metadata, exact license/NOTICE/branding-policy
bytes, package inventory and source-check inputs; then installs the wheel without
network dependency resolution in a fresh virtual environment. CLI and pure-core
conformance smoke tests run outside the checkout. Reports include artifact hashes
and the build-tool version. This is a functional round-trip, not a claim of
bit-for-bit reproducible builds across arbitrary platforms or build backends.

CI separately runs the operational lifecycle from installed bytes with
`reference_runtime` removed, and executes actual rootless Podman. Those tests
remain required; an import/CLI smoke test is not a substitute.

## Publishing

Complete [PUBLICATION](PUBLICATION.md) first. The maintainer reviews the exact
commit's CI, provenance, redacted history audit and external publication gates.
Create the matching annotated tag on that commit, verify its target, then publish
release notes with compatibility, supported scope, known limits and artifact
SHA-256 values. Protect release tags against replacement/deletion. Do not retag
an existing release; issue a new version for corrections.

Registry publication is optional and separate. Confirm ownership of the actual
package namespace, inspect the final archives, and use a separately approved
publication workflow/credential. The repository's CI only builds/tests artifacts;
it does not upload to PyPI, enable public visibility or grant release authority.

## 1.10.1: audited recovery and worker fixes

- Exact-bound owner reverification for completed observations; the retired generic retry never grants authority.
- Identical validation for staged/final edits, adapter/model-bound smoke attestations, safe OS locks and live subprocess output limits.
- Source and built-archive identity scans, consumer-neutral portable transfer tooling and public-origin provenance locks.
- Real adapter and pipe regressions preserve uncertain-call fences, frozen assertions, budgets and original receipts.

This release does not rewrite prior history, publish the repository, establish legal clearance or claim a live target-host smoke. Existing experimental worker attestations require renewed commissioning after code review; unknown old turns still require explicit owner reconciliation/retry.

## 1.10.0: shared autonomy and worker integration

- Purpose-bound work-plan authorization and separate exact-candidate merge approval.
- Typed, persisted technical recovery without relaxing scope, risk, budget or uncertain-effect gates.
- A portable controller-brokered worker package, included in source locks, distributions and runtime fingerprints, with credential-free inspection of the pinned official CLI capabilities.
- Shared scenarios exercise the actual production adapters. Package and controlled-runtime tests do not establish live model convergence or authorize deployment.

Existing wire contract identities remain unchanged. Historical candidate approvals
do not become work-plan authority; an eligible owner-operated runtime upgrade and
fresh owner continuation remain required.

## 1.9.2: publication preparation

- Modern SPDX packaging metadata and explicit license-file inclusion.
- Source-archive to wheel to clean-install checks and negative regression tests.
- Pinned GitHub Actions, bounded job execution, issue forms and maintainer routing.
- Read-only settings audit and a manual administrator configuration guide; no
  automated settings changes, visibility changes or policy bypass.
- Correctly staged publication gates, current support policy, provenance and
  trademark-permission routing, and consumer-neutral public documentation.

The runtime's effect/receipt, approval binding, recovery, provider dispatch,
wire-contract and persistence semantics are unchanged.

## 1.9.1

Fixes environment-dependent redaction corrupting run IDs and hashes in readable
output. Credential inference uses name suffixes and short inferred values match
whole tokens. Explicit credentials retain substring redaction before truncation;
masking is a single pass so replacement markers cannot be corrupted.

## 1.9.0

Adds read-only operator explanations, readable CLI formats, explicit result
location, generated workflow documentation, and a local UI overview. JSON
remains the default. See [OPERATOR-EXPERIENCE](OPERATOR-EXPERIENCE.md).
