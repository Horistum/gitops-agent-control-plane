# Publication readiness

The reference is standalone, Apache-2.0 licensed and records Horistum provenance.

## Defined controls

The following policies are defined:

1. private vulnerability reporting policy: `.github/SECURITY.md`;
2. repository and contract release/versioning policy: `docs/RELEASES.md`;
3. best-effort support policy: `SUPPORT.md`;
4. licensing/provenance: `LICENSE`, `NOTICE`, `TRADEMARKS.md`, `CONTRIBUTING.md`.

## Remaining operational gates before public visibility

1. enable GitHub Private Vulnerability Reporting and test it from outside the Horistum organization;
2. run a clean-room clone/validation with no Horistum organization access;
3. review Git history, CI logs and release artifacts for secrets or private implementation details;
4. choose a stable public namespace if JSON Schema `$id` values are added before the first tag.

## Clean-room acceptance

Using public-only access:

```bash
./scripts/agentctl bootstrap check
./scripts/agentctl validate
./scripts/agentctl conformance
```

Acceptance requires **all documented conformance scenarios** to reach their documented outcomes on every supported Python version, with no private dependency or credential. The scenario set is discovered from `examples/scenarios/`; publication checks must not silently assume a stale hard-coded count.

## First public release

After the remaining gates:

1. make the repository public;
2. repeat clean-room validation;
3. tag the exact tested commit as `v0.1.0`;
4. publish release notes under `docs/RELEASES.md`.

## Horistum positioning

The reference remains an implementation-neutral open technical asset initiated and maintained by Horistum. It should not expose or masquerade as a private/commercial runtime.
