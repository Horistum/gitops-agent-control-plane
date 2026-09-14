# Security model

The primary threat is an autonomous component that can both change a product and weaken the evidence or authority used to approve that change.

## Demonstrated controls

Contract v5 demonstrates:

- one memoized segment-aware path matcher for authority, writes and risk classification;
- non-empty product-authority snapshots;
- separate developer/tester write domains;
- immutable owner-controlled baseline-test files;
- controller-side verification definitions that are not copied into the candidate workspace;
- runtime-generated property-style probe cases instead of published fixed input tuples;
- acceptance negative controls that must fail on the baseline implementation;
- a trusted verifier parent that never imports candidate code;
- candidate execution in a separate child process;
- an HMAC-authenticated receipt challenge delivered to the verifier parent over a private inherited control FD rather than argv or environment;
- exactly one accepted receipt line per probe;
- exact candidate/merge SHA binding for controller probe evidence;
- computed review from controller-observed probe evidence;
- reachable LOW, MEDIUM and HIGH policy behavior;
- pre-write change-budget and risk-ceiling gates;
- durable merge intent plus cross-process recovery;
- fail-closed JSON Schema keyword validation.

## Candidate-process JUnit is diagnostic, not authoritative

JUnit output, test names, counts and assertions are produced by a Python process that imports code from the candidate write envelope. Candidate code can therefore influence Python globals, assertion helpers or XML serialization in that process.

Contract v5 treats JUnit as **not authoritative**. A green JUnit file is supplemental diagnostic evidence and cannot authorize a candidate by itself.

The conformance suite includes direct forgery cases for empty test bodies, `unittest` monkeypatching and forged JUnit output. All remain blocked by controller probes.

## Signed verifier-parent receipt boundary

The controller creates a fresh receipt key/challenge for each probe. The key and challenge are serialized to an anonymous pipe and the read side is inherited only by the trusted verifier parent through a **control FD**. They are not placed in `sys.argv` or the environment.

The verifier parent reads and closes that FD before creating any candidate child. It never imports candidate code. Candidate children receive only their current generated input and cannot see the receipt key, future cases or oracle definition through the normal protocol.

The verifier parent evaluates the raw child outcome against its oracle, creates the final receipt and authenticates the canonical receipt with HMAC-SHA256. The controller requires exactly one receipt line, verifies the HMAC and verifies the challenge/probe identity before treating the result as completed.

This closes the previous construction where the candidate could read a nonce from worker argv and print a fake success receipt.

## Randomized oracle boundary

Probe definitions no longer publish literal `args` plus literal expected return values. They declare a case generator and an invariant/oracle. Fresh cases are generated separately for baseline negative control, candidate verification and post-merge verification.

For the reference product, examples include randomized whitespace/name inputs with invariants such as:

- `normalize_name(x) == " ".join(x.split())`;
- `greet(x) == "Hello, " + " ".join(x.split()) + "!"`;
- blank inputs raise `ValueError`;
- randomized non-string inputs raise `TypeError`.

This prevents a lookup table for published fixture inputs from satisfying conformance. It is not proof against an adversarial implementation that can inspect or attack the verifier process on the same host.

## Remaining hostile-code boundary

The standalone verifier still runs candidate Python on the same operating-system host. A malicious same-user process may attempt `/proc` inspection, kernel/process attacks, resource abuse or other techniques outside the protocol model.

Therefore contract v5 **does not claim a complete hostile-code trust boundary**. For arbitrary model-generated or malicious candidate code, production verification must run in a container/VM/remote verifier with a result channel the candidate cannot access or impersonate.

## Local executor is not a security sandbox

The standalone executor is restricted to deterministic `trusted-fixture` proposals. It provides controller wall-clock timeout, CPU limits derived from policy, a scrubbed environment, basic process limits, and process-group descendant cleanup.

It is **not a security sandbox** and does not provide filesystem, network, kernel or VM isolation.

## Event-chain limitation

`events.jsonl` is hash-linked. It detects accidental corruption and edits where hashes are not recomputed.

It is **not an authenticity mechanism**. A party that can rewrite the entire evidence directory can rewrite events and recompute the chain.

A production system must anchor the event/evidence tip outside the mutable evidence directory, for example with a trusted remote state store, signed checkpoint, transparency log or independently controlled verifier.

## Product authority

Structured enforcement inputs are JSON authority files such as roadmap, forbidden rules, release state, quality gates and verification probes. Human-readable `authority.md`, `architecture.md` and free-form `forbidden_directions` are context rather than silently executable natural language.

## Security reporting

Repository vulnerability reporting is documented in `.github/SECURITY.md`.
