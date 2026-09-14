# Security model

The primary threat is an autonomous component that can both change a product and weaken the evidence or authority used to approve that change.

## Demonstrated controls

Contract v3 demonstrates:

- a single segment-aware path matcher for authority, writes and risk classification;
- product authority snapshotting with a non-empty file set;
- separate developer and independent-tester write domains;
- immutable protected baseline-test files;
- baseline JUnit identity preservation;
- roadmap acceptance criteria mapped to required executable test identities;
- test evidence bound to exact Git SHAs;
- computed review rather than hard-coded approval booleans;
- reachable LOW, MEDIUM and HIGH risk behavior;
- pre-write change-budget and risk-ceiling gates;
- a real process restart around a durable pending merge effect;
- duplicate merge-effect detection through a stable effect identity;
- JSON Schema validation of emitted safety/evidence artifacts.

## Local executor is not a security sandbox

The standalone executor exists only for deterministic trusted fixtures shipped in this repository.

It provides:

- a wall-clock timeout;
- a scrubbed environment;
- basic process resource limits where the host supports them.

It does **not** provide:

- filesystem isolation;
- network isolation;
- kernel/container isolation;
- protection from malicious candidate code.

Accordingly the standalone runtime rejects non-`trusted-fixture` proposal sources. Connecting a model or other untrusted code producer requires a different executor providing a real container/VM/sandbox boundary.

## Event-chain limitation

`events.jsonl` is hash-linked. It detects accidental corruption and edits where hashes are not recomputed.

It is not an authenticity mechanism. A party that can rewrite the entire evidence directory can rewrite events and recompute the chain.

A production system must anchor the event/evidence tip outside the mutable evidence directory, for example with a trusted remote state store, signed checkpoint, transparency log or another independently controlled verifier.

## Test trust boundary

The protected baseline test file is owner-controlled. The developer cannot modify tests. The independent tester may create only policy-approved acceptance-test files.

A green process exit is not enough. Candidate review checks baseline identities, required acceptance identities, protected-test digests, aggregate counts and exact Git-SHA binding.

## Security reporting

Repository vulnerability reporting is documented in `.github/SECURITY.md`.
