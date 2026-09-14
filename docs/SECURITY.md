# Security model

The primary threat is an autonomous component that can both change a product and weaken the evidence or authority used to approve that change.

## Demonstrated controls

Contract v4 demonstrates:

- one memoized segment-aware path matcher for authority, writes and risk classification;
- non-empty product-authority snapshots;
- separate developer/tester write domains;
- immutable owner-controlled baseline-test files;
- product-authored verification probes protected by the authority snapshot;
- acceptance negative controls that must fail on the baseline implementation;
- one fresh process per controller probe;
- a controller completion receipt so `exit(0)` alone is not success;
- exact candidate/merge SHA binding for controller probe evidence;
- computed review from controller-observed probe evidence;
- reachable LOW, MEDIUM and HIGH policy behavior;
- pre-write change-budget and risk-ceiling gates;
- durable merge intent plus cross-process recovery;
- fail-closed JSON Schema keyword validation.

## Candidate-process JUnit is diagnostic, not authoritative

JUnit output, test names, counts and assertions are produced by a Python process that imports code from the candidate write envelope. Candidate code can therefore influence Python globals, assertion helpers or XML serialization in that process.

Contract v4 treats JUnit as **not authoritative**. A green JUnit file is supplemental diagnostic evidence and cannot authorize a candidate by itself.

The conformance suite includes three explicit forgery cases:

1. acceptance tests have the correct names but empty bodies;
2. candidate package initialization monkeypatches `unittest` assertions;
3. candidate code forges a five-test JUnit document although no acceptance test file exists.

All three must remain blocked by controller probes.

## Controller probe boundary

Controller probes are defined under `.agent-control/verification-probes.json`, outside proposal write scope. The worker loads the target source file directly rather than importing the candidate package, captures selected stdlib function identities before candidate import, runs one probe per fresh process and emits a nonce-bound completion receipt only after the probe protocol completes.

This materially reduces accidental and demonstrated in-process evidence forgery. It does **not** create a complete hostile-code trust boundary. Python code in the worker process can still attempt process-level attacks, introspection or other behavior unavailable to a fully isolated verifier.

For arbitrary model-generated or malicious candidate code, a production implementation must execute verification behind a real isolation boundary and should treat evidence as trusted only after it crosses that boundary.

## Local executor is not a security sandbox

The standalone executor is restricted to deterministic `trusted-fixture` proposals.

It provides:

- controller wall-clock timeout;
- CPU limit derived from that policy timeout;
- scrubbed environment;
- basic process resource limits;
- dedicated process group and descendant cleanup.

It does **not** provide filesystem, network, kernel or container isolation. Connecting an external model/untrusted producer directly to it remains unsupported.

## Event-chain limitation

`events.jsonl` is hash-linked. It detects accidental corruption and edits where hashes are not recomputed.

It is **not an authenticity mechanism**. A party that can rewrite the entire evidence directory can rewrite events and recompute the chain.

A production system must anchor the event/evidence tip outside the mutable evidence directory, for example with a trusted remote state store, signed checkpoint, transparency log or independently controlled verifier.

## Product authority

Structured enforcement inputs are JSON authority files such as roadmap, forbidden rules, release state, quality gates and verification probes. Human-readable `authority.md`, `architecture.md` and free-form `forbidden_directions` are context rather than silently executable natural language.

## Security reporting

Repository vulnerability reporting is documented in `.github/SECURITY.md`.
