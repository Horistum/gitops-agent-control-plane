# FlowAI-Control 0.3.0 limitations relevant to this reference

The purpose of this file is to prevent the reference repository from claiming capabilities the
engine does not currently have.

## 1. Upstream v0.3.0 upgrade helper conflates runtime source and control repo

Normal runtime construction correctly treats:

- `product_repo` as product source;
- `control_repo` as state/command repository.

But `scripts/upgrade_v030.py` validates the checked-out source commit by querying merged pull
requests in the configured `control_repo`. That assumption is valid for the original Horistum pilot,
where `FlowAi-control` was both source and control repository, but not for a tenant-separated control
repo.

**Reference response:** `scripts/install_runtime.py` installs and verifies the exact pinned
`Horistum/FlowAi-control` source commit directly. It does not call `upgrade_v030.py`.

## 2. Historical commissioning scripts are pilot-specific

Several 0.2.x commissioning scripts intentionally contain audited `milank78git/FlowAi` /
`milank78git/FlowAi-control` identities and historical baseline SHAs. They are evidence/recovery
artifacts, not generic onboarding tools.

**Reference response:** do not use them for new tenants.

## 3. Fresh installation is still an owner-operated trust-boundary action

GitHub Goal Issues control engineering work after activation. Installing controller binaries,
choosing a test image, authenticating GitHub/Codex, establishing branch governance and approving the
first fingerprint remain explicit operator actions.

This is a safety boundary, not missing autonomous polish.

## 4. Goal Issue v1 labels are protocol-visible

The parser expects the exact v1 section labels currently produced by the included Czech Issue Form:

- `Cíl`
- `Položky roadmapy`
- `Nejvyšší přijatelné riziko`
- `Automatický merge`
- `Podmínka dokončení`
- `Zakázané směry`
- `Potvrzení`

Translating these labels without changing/versioning the engine parser breaks authorization.

**Reference response:** preserve the exact Issue Form until a future protocol version separates
machine field identifiers from display labels.

## 5. JUnit discovery path is opinionated

FlowAI-Control 0.3.0 discovers executable test identities only from:

```text
**/build/test-results/**/*.xml
```

A Python project using ordinary unittest/pytest output therefore needs a JUnit-producing wrapper or
configuration that writes into this layout.

**Reference response:** the minimal product includes `ci/run_tests.py`.

## 6. Base branch is `main`

Policy validation in 0.3.0 requires `base_branch == "main"`.

## 7. Single controller identity, not a distributed lease

The state store fences another `controller_id`, but it is intentionally not a multi-host leader
election protocol. Two machines with the same identity must not run simultaneously.

## 8. Product CI/governance is an external prerequisite

The controller can verify governance and required checks, but the tenant still has to create the
trusted workflow and server-side branch/ruleset configuration. This reference provides the sample
workflow and a deterministic ruleset creation helper.

## 9. Exact compatible pin will become stale by design

The source SHA in `COMPATIBILITY.json` should not update automatically. A newer FlowAI-Control
release requires a reference PR that updates the pin, checks policy/schema compatibility and reruns
reference validation.
