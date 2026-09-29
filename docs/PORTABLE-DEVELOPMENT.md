# Portable development and repository alignment

A trusted consumer may be the primary development checkout for shared behavior.
This reference publishes the reusable implementation and a separate operational
adapter. Neither controller launches the other. Both execute their own persistence,
authentication and deployment around the same portable source.

## Ownership

| Area | Shared exact bytes | Adapter responsibility |
|---|---|---|
| `control_plane_core` | Workflow, work/merge bindings, acceptance, CI classification, typed recovery | Authenticate observations and execute authorized effects |
| `agent_worker` | Optional brokered Codex session, source tools, protocol bounds and replay | Supply exact Git source, policy/scope checks, reservations and role separation |
| Transfer and contract tooling | Transfer script, paired adapter script and their portable tests | Run the local matrix in each repository and paired comparison before export |
| Consumer runtime | No | Product authority format, storage profile, owner channel and deployment |
| Reference runtime | No | Generic operational policy, local state, provider adapters and reference service |

Schema 2 of `CONTROL-CORE.lock.json` includes every portable source file, package
identity, allowlisted origin repository and exact source commit. Each repository
checks its lock without network access or access to a private consumer checkout.
A provenance lock identifies bytes; it does not prove owner review, remote
availability or target-host validation.

## Develop once, export explicitly

Start both checkouts from reviewed main. Develop shared behavior in the primary
checkout, and implement necessary adapter changes in both projects. Keep private
product paths, local policy and deployment details out of portable packages and
public documentation. The initial alignment must import the reviewed reference
baseline before consumer changes are exported back.

1. Run focused tests, both complete suites and the actual paired adapter matrix.
2. Commit finished portable files in the development checkout and publish that
   commit on its review branch. The origin revision must be retrievable by the
   reviewers responsible for that source.
3. Use `--record` to bind that already existing commit in the source lock. Commit
   the lock and release metadata in a following commit; there is no self-reference.
4. Export into the other checkout, review the diff, update its adapter/schema/
   package metadata and open a linked PR. Preserve licenses and NOTICE.
5. Require both CI runs and owner review. Consumer deployment retains its own gates.

For steps 3 and 4, while the development HEAD is the portable source commit:

```bash
portable_source_sha="$(git -C "$portable_source" rev-parse HEAD)"
python3 "$portable_source/scripts/sync_control_core.py" \
  --record --target "$portable_source" \
  --repository "$portable_origin" --commit "$portable_source_sha"
python3 "$portable_source/scripts/sync_control_core.py" \
  --source "$portable_source" --target "$portable_target" \
  --repository "$portable_origin" --commit "$portable_source_sha" --export-only
```

Set the three path/origin variables explicitly for the intended reviewed pair;
`--repository` accepts only the script's declared allowlist. A reviewed import
from this project uses origin `Horistum/gitops-agent-control-plane`. Source
portable files must equal the committed Git blobs. The source lock may be an
uncommitted following change because it is outside its own inventory. If HEAD
has advanced, export from a temporary checkout of the exact portable revision.

Initial lock adoption uses `--adopt-identical` only after an independently
reviewed byte-for-byte match. The flag cannot overwrite divergent local work.
Normal transfers require a matching existing lock. Dirty source, unknown origin,
partial unmanaged targets, changed target bytes, symlinks and unexpected files
stop before replacement. Detected write errors restore previous files and lock
where the filesystem permits. Power loss is detected by the next lock check;
this is not an atomic multi-file filesystem transaction.

## Required verification

Each checkout runs:

```bash
python3 scripts/sync_control_core.py --check
python3 -m unittest discover -s tests -v
```

With both trusted checkouts available:

```bash
python3 scripts/check_workflow_adapters.py \
  --reference /path/reference-checkout --consumer /path/consumer-checkout
```

The matrix drives production controllers with real Git and subprocess test
execution. It compares routes, invalidated evidence and outcomes across full and
adaptive graphs, repair, stale verification, scope rejection, receipt replay,
uncertain dispatch, separate work/merge authority and trusted CI classifications.
See [adapter capability audit](ADAPTER-CAPABILITY-AUDIT.md) for coverage limits.
Each repository runs its local matrix in normal CI; public CI never requires
credentials for a private checkout. A paired run adds cross-adapter comparison.
Controlled model/HTTP peers do not establish live provider or product quality.
Package and installed-release checks remain separate gates.

A product worker cannot export shared code, merge controller PRs or deploy its own
runtime. These remain owner-operated controller maintenance actions.

## Public provenance boundary

`PORTABLE-ORIGINS.json` is reviewed checkout-specific configuration. The public reference permits only its public repository identity; private development origins belong only in the consumer checkout. Portable Python code never hardcodes a private origin or imports a private adapter. The consumer supplies its reviewed local `tests/workflow_adapter_driver.py`; the portable harness compares its results with the reference driver.

When exporting into a public candidate, use `--export-only`. It copies committed portable bytes and leaves the old target lock untouched. The reported `record_required` means the target is deliberately not releasable yet. Commit the portable files in the target (without staging a private provenance lock), then run:

```bash
python3 scripts/sync_control_core.py --record \
  --repository Horistum/gitops-agent-control-plane --commit "$(git rev-parse HEAD)"
```

Commit that new lock separately. The two repositories must have identical portable file hashes, package versions and contracts; their origin repository and source commit may differ. The reference pin identifies the actual committed reference bytes, while the consumer retains the private development origin. Never redact or relabel an existing commit identity. A reference import is still subject to owner review and CI before merge.
