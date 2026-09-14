# Executable showcase

The quickest way to understand the reference is to run the scenarios rather than read a diagram and politely believe it.

## Happy path

```bash
./scripts/agentctl demo happy-path
```

The runtime:

1. copies `examples/minimal-product` into an isolated run workspace;
2. initializes a real Git repository and records the exact baseline SHA;
3. runs the three baseline tests;
4. snapshots product authority by content digest;
5. discovers `EXAMPLE-001`;
6. creates a bounded plan;
7. creates developer proposal evidence and a unified patch;
8. checks every proposed path against write and authority boundaries;
9. creates a real candidate commit;
10. runs five executable tests;
11. records tester and reviewer evidence;
12. evaluates risk and merge authority;
13. creates a real non-fast-forward merge commit;
14. runs post-merge tests;
15. verifies the hash-linked event log and emits terminal evidence.

The candidate and merge SHAs are actual Git object identities from that run.

## Forbidden path

```bash
./scripts/agentctl demo forbidden-path
```

The developer proposal intentionally targets `.agent-control/architecture.md`.

Expected terminal state:

```text
BLOCKED_POLICY
```

There is no candidate SHA and no merge SHA. The useful property is not that the runtime can notice an ugly diff later. It prevents an unauthorized authority mutation from becoming a candidate at all.

## Test failure

```bash
./scripts/agentctl demo test-failure
```

The candidate deliberately implements `Hi, ...` while executable acceptance tests require `Hello, ...`.

Expected terminal state:

```text
FAILED_VERIFICATION
```

A candidate commit exists, because a candidate is allowed to be wrong. A merge does not exist, because reasoning cannot overrule failing executable evidence.

## Human gate

```bash
./scripts/agentctl demo human-gate
```

The proposal is functionally green but also touches a path classified as critical.

Expected terminal state:

```text
NEEDS_DECISION
```

The run emits `human-decision.json` containing the exact candidate SHA and risk. The reference does not silently treat a successful test as authorization to cross a higher-risk boundary.

## Crash recovery

```bash
./scripts/agentctl demo crash-recovery
```

The runtime persists a merge-effect intent and request hash, simulates a process restart, reloads durable state, proves that the pending effect identity still matches, and continues without inventing a second merge request.

The evidence includes:

```text
merge-intent.json
recovery.json
events.jsonl
```

This demonstrates why durable intent must exist before external effects.

## Full matrix

```bash
./scripts/agentctl conformance
```

The matrix asserts both positive and negative behavior. An implementation that can complete the happy path but cannot reject forbidden paths is not conformant.
