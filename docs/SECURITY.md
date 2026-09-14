# Security model

The primary threat is an autonomous component that can both change a product and weaken the authority or evidence used to approve that change.

## Demonstrated controls

Contract v6 demonstrates:

- one memoized segment-aware path matcher for authority, writes and risk;
- separate developer/tester write domains and protected baseline tests;
- controller-side verification definitions omitted from the candidate workspace;
- a generic product-authored generator/invariant DSL rather than product-specific control-plane oracles;
- **case-level negative control**: every generated acceptance case must complete and fail on baseline;
- a trusted verifier parent that never imports candidate code;
- candidate execution in separate child processes;
- HMAC-authenticated parent receipts with challenge/control material delivered through an inherited **control FD**, not candidate argv/environment;
- exactly one accepted final receipt per probe;
- exact candidate/merge SHA binding;
- pre-write budgets/risk gates, durable merge intent and process recovery;
- fail-closed JSON Schema validation for emitted safety/evidence artifacts, including authority snapshots, protected-test snapshots, merge intent and human decisions.

## JUnit is diagnostic and not authoritative

Candidate-process JUnit imports candidate code and can therefore be influenced through assertions, imports or XML serialization. It is **not authoritative** and cannot override controller probe failure.

## Signed verifier-parent receipt boundary

The controller generates a fresh receipt key/challenge per probe. The executor starts the trusted parent reader before writing the control payload, so payload growth cannot deadlock on an unread pipe buffer. The parent consumes and closes the control FD before candidate children are started.

Candidate children receive only their current generated args/kwargs. Their stdout is treated as untrusted observation and is not forwarded into the parent final-receipt stream. The parent owns oracle evaluation and signs the canonical final receipt with HMAC-SHA256. The controller requires exactly one receipt and verifies the HMAC, challenge, probe ID and protocol version.

The conformance case `receipt-injection` attacks this **current protocol** by writing a fake final-receipt line from candidate code. Conformance requires proof that at least one injection attempt was observed in child stdout and that the parent-facing receipt remained singular and valid.

The child raw-outcome channel is still an observation produced in the same process that executes candidate Python. V6 does not promote that fact into a hostile-code guarantee. A same-host malicious process may attempt process/file-descriptor/OS attacks beyond the fixture protocol.

## Generic invariant boundary

Probe definitions describe generic generators and expressions rather than literal input/output tuples or product-named runtime functions. The current DSL supports multiple positional args, named kwargs, choices, integers, booleans, whitespace/token text generation, and expression composition such as arg/kwarg lookup, split, join, concat, strip, case conversion and length.

This makes the control plane reusable without embedding `greet`-specific logic. It is intentionally a small declarative DSL, not arbitrary executable oracle code.

Fresh finite cases reduce simple lookup-table overfitting but do not prove correctness. The `probe-aware` conformance fixture deliberately satisfies public diagnostics and a narrow ASCII subset while the current product-owned unicode invariant rejects it.

## Remaining hostile-code boundary

The local executor is **not a security sandbox**. Candidate Python still runs on the same operating-system host. Production use with arbitrary model-generated or malicious code requires a container, VM or remote verifier whose process/filesystem boundary and result channel are outside candidate control.

## Event-chain limitation

`events.jsonl` is hash-linked consistency evidence. It is **not an authenticity mechanism** against a party that can rewrite the entire evidence directory and recompute hashes. Production systems need an independent signed/external anchor.

## Product authority

Structured enforcement inputs are roadmap, forbidden rules, release state, quality gates and verification definitions. Human-readable Markdown/prose is context, not silently executable policy.

## Security reporting

Repository vulnerability reporting is documented in `.github/SECURITY.md`.
