# Merge receipt persistence and recovery

The standalone reference runtime publishes a complete, schema-valid merge
receipt before it acknowledges consumption of the pending merge effect. Both
`merge-evidence.json` and its per-item projection contain the exact base,
candidate, merge, two observed parents, request hash and effect count at their
first publication. Identity fields are not added in a second enrichment pass.

## Commit order

1. Read the merge's actual Git parents and verify the exact authorized base and
   candidate. Verify the saved intent hash and exactly one matching Git effect.
2. Construct and validate the complete receipt, without advancing state.
3. Atomically publish the canonical receipt, then its per-item projection.
4. Set `merge_sha`, clear `pending_effect`, enter `POSTMERGE_VERIFY`, append the
   consumption event and publish state.
5. Only then allow the `after-merge-receipt-before-postmerge` crash hook to fire.

The hook now follows the normal superclass chain. The public engine no longer
bypasses the recovery facade to enrich an already acknowledged receipt.

JSON publication uses a temporary file in the destination directory, file
`fsync`, atomic replacement and directory `fsync`. Event appends are flushed and
synced before publishing their state checkpoint. This is a single-writer local
filesystem protocol, not a multi-file transaction or a multi-writer database.
An interrupted/torn event record fails event-chain validation; automatic repair
of an arbitrary damaged event log is not claimed.

## Recovery behavior

If the pending effect is still present, the normal effect reconciler observes
and consumes the existing merge instead of creating another merge. Any receipt
written before that interruption can safely be replaced by the complete receipt
for the same verified effect.

Before post-merge verification, the runtime also validates the saved per-item
intent, its request hash, the active state's base/candidate/branch, the actual
Git parents, the unique effect occurrence and existing receipt projections.
Missing receipt projections, or legacy receipts missing only the four identity
fields, can be reconstructed from these independently checked inputs. Existing
contradictory fields, malformed JSON, unsupported fields or missing required
intent block completion as `BLOCKED_POLICY`. Contradictory evidence is retained,
not overwritten to make validation appear successful.

The canonical and per-item intent must agree when both exist. A per-item intent
is required for reconstruction. This change does not migrate completed historic
runs or automatically edit consumer source pins and installed runtimes.

## Verification and boundaries

`tests/test_merge_receipt_recovery.py` interrupts execution before and after both
receipt writes, before and after the consumption event and state publication,
and during receipt reconstruction. Fresh public `resume_run` calls must finish
with schema-valid evidence and exactly one merge effect. Separate cases exercise
legacy/missing projections, contradictory receipts, corrupted intents and
atomic-replacement failures. The existing exact-parent and named-crash tests
remain applicable.

These tests use real local Git fixture repositories and simulated process
interruption. They are not hardware power-loss certification, a security sandbox,
or proof of evidence authenticity against an actor able to rewrite the entire
run directory and Git repository. No live model credentials are needed.
