# Evidence model

## Authority evidence

Authority snapshots enumerate real matching files using the exact same segment-aware path matcher used by write gates. The runtime fails if the configured authority snapshot or any configured authority pattern matches no file.

## Test evidence

For each test run the controller records:

- exact tested Git SHA;
- exit code and timeout flag;
- testcase count and identities;
- failures/errors/skips;
- stdout/stderr digests;
- executor isolation metadata.

Before each run, stale JUnit output is removed. A failed runner that writes no new XML therefore cannot inherit old testcase identities.

## Candidate review evidence

Review is derived from the evidence predicates documented in `MODEL.md`. Protected baseline tests are both content-digested and identity-checked. Acceptance coverage is derived from roadmap acceptance → test identity mappings.

## Effect evidence

Merge intent is persisted before effect execution. Merge commits carry a stable effect request ID. Recovery checks the Git history for that ID and requires one occurrence before consuming the effect.

## Event chain: consistency, not authenticity

Events are hash-linked. This detects corruption or edits where hashes are not recomputed.

The chain is deliberately **not described as tamper-proof**. There is no secret key or external anchor in the standalone reference. A full evidence-directory rewriter can recompute the chain and terminal tip.

Production systems need an independent anchor/signature/transparency mechanism.

## JSON Schema

Core safety artifacts and individual events are validated against Draft 2020-12 schemas during conformance.
