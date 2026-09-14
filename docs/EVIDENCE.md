# Evidence model

## Authority and protected-test evidence

Authority snapshots enumerate real matching workspace files with the same matcher used by policy gates and separately bind the controller-side verification-definition digest. Protected-test snapshots record byte digests of owner-controlled baseline tests.

Contract v6 gives both artifact families explicit JSON Schemas; they are not merely opaque objects in the evidence directory.

## Diagnostic JUnit

`test-baseline.json`, `test-candidate.json` and `test-postmerge.json` record exact SHA, exit/timeout state, testcase identities/counts, stdout/stderr digests and executor metadata. Stale JUnit is deleted before execution.

These artifacts carry `authoritative: false` because candidate code executes in the same process that produces those diagnostics.

## Signed verifier evidence

`probe-baseline.json`, `probe-negative-control.json`, `probe-candidate.json` and `probe-postmerge.json` record verifier-definition identity, probe identities, one authenticated parent receipt per probe and structured per-case results.

Each case records input digest, child exit status, raw-outcome count, observed outcome, pass/fail reason and how many candidate **final-receipt injection attempts** were observed in child stdout. This lets conformance prove an attack path actually executed instead of inferring it from a scenario name.

The receipt schema validates protocol, challenge, probe identity, case count and case rows. Semantic HMAC validation remains a controller operation because the schema does not possess the per-run secret key.

## Case-level negative control

New acceptance probes first run on baseline. Negative control succeeds only when all probe receipts complete and **every generated acceptance case** is rejected. Evidence records total case count and `negative_control_all_cases_rejected` explicitly.

Regression probes are separate and must pass on baseline.

## Generic oracle evidence

Product authority defines generators and declarative expressions through the generic probe DSL. The controller/verifier runtime no longer contains product-specific `greet`/`normalize_name` oracle functions. Fresh cases are generated separately for baseline, negative-control, candidate and post-merge phases.

## Durable/human evidence

Contract v6 adds schema coverage for `merge-intent.json`, `human-decision.json`, requests, proposals, role artifacts and fault-injection evidence in addition to merge/recovery/state/terminal evidence. The core authority, verification, risk and recovery path is therefore schema-checked rather than only selected endpoints.

## Event chain

Events are hash-linked consistency evidence, not authenticity. A writer able to replace the whole evidence directory can recompute an unkeyed chain. Production systems require an independent signed/external anchor.

## Scope boundary

Candidate-child raw output remains an untrusted same-host observation. The trusted verifier parent evaluates it and signs the resulting receipt within the deterministic fixture model. This is not hostile-code isolation; production verification requires a container/VM/remote boundary and independently controlled result channel.
