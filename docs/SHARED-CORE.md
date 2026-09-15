# Shared implementation and runtime profiles

The canonical reusable Python implementation is `control_plane_core`, version
`1.1.0`, implementing deterministic decisions from `autonomous-control-plane/v1`.
The standalone engine imports it directly. `Horistum/FlowAi-control` imports the
same package bytes, pinned to a source commit in `CONTROL-CORE.lock.json`.

## Ownership

| Concern | Shared implementation | Runtime responsibility |
|---|---|---|
| Work selection | Validated dependency graph, readiness, bounded requested scope | Read and authenticate product intent; normalize JSON or Flow YAML |
| Completion | Verified, scoped, idempotent completion and goal projection | Persist progress only after exact merge and post-merge verification |
| Risk | Hard risk ceiling, automatic merge ceiling, mandatory human threshold | Authenticate revision-bound human decisions |
| Changes | Relative path and allow/protect/deny decisions | Validate expected bytes, size, filesystem boundaries and apply proposals |
| Merge | Exact base/candidate and two-parent identity proof | Local Git CAS or protected GitHub merge API; durable operation intent |
| CI | Latest successful named check from the configured provider identity | Obtain check observations from authenticated provider APIs |

The core has no process execution, Git writes, network, credentials or model
provider. Models cannot directly create effect authority. The runtime adapter
must obtain observations from the declared trusted source; passing a model's
claimed `verification_passed` boolean does not constitute verification.

`goal_projection()` without an intent graph computes completion only and grants
no selection authority. Prose remains reasoning context. A risk above the hard
goal ceiling is blocked; ordinary approval cannot enlarge that goal.

## Deliberate profile differences

The reference uses `property-probe/v6`, fixture providers, retained candidate audit
refs, local Git and controller-owned `release-state.json`. Flow uses a Codex
provider, rootless Podman, protected GitHub PRs and durable `loop-state`. Its
product-authored YAML release metadata is a lifecycle assertion, not the
controller's completion ledger. Its `flowai-yaml/v1` profile normalizes declared
dependencies and ordered implementation slices and verifies external predecessor
merges against the current base and trusted post-merge checks.

The fixture retains its property-probe negative controls and promotion. Core 1.1.0 additionally supplies `verification-evidence/v1`: executable AC/test bindings, declared new-behavior versus regression semantics, typed goal conditions and externally evaluated process/artifact predicates. Flow 0.5.0 uses these with its counterfactual/regression and rootless CLI adapters, promotes accepted independent test files, and verifies the actual merge again.

The reference also provides `agentctl verify-cli --trusted-fixture` as a separately runnable external process observation profile. This command is not a production sandbox and does not replace the standalone engine's configured property-probe profile. `docs/LIMITATIONS.md`, including raw-outcome-forgery, remains applicable to that legacy profile. Finite external observations do not prove every possible product behavior.

## Reproducible adoption

On a clean checkout of a reviewed reference commit:

```bash
python3 scripts/sync_control_core.py --source . --target ../FlowAi-control --commit FULL_REFERENCE_COMMIT
cd ../FlowAi-control
python3 scripts/sync_control_core.py --check
python3 -m unittest discover -s tests -v
python3 scripts/build_release_manifest.py
```

The synchronization is a development operation, never a runtime auto-update.
Review the consumer changes and run CI before deployment. The script rejects a
dirty source, non-exact revision, linked package or a locally diverged consumer.
The lock inventories all core files and retains the Apache license and NOTICE.
Both repositories execute the same `control_plane_core.conformance` vectors,
plus their runtime integration suites. The consumer fingerprint includes the
core and its nested runtime dependencies, so core changes invalidate activation.

## Validation boundary

`python3 -m control_plane_core.conformance` tests the pure contract.
`./scripts/agentctl validate` also exercises the standalone state machine,
security scenarios and crash recovery. Flow's full suite exercises its adapters
and real local Git interactions. A live Legion installation, live Codex response
and real Flow product build remain deployment gates on that host.
