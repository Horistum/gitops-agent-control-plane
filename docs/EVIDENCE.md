# Evidence model

## Evidence classes

### Authored authority

Goal, roadmap item, architecture and policy.

These define the question the system is allowed to answer.

### Reasoning artifacts

Role discovery, plan, developer proposal, tester assessment and review.

Useful explanations, but not execution proof.

### Controller evidence

Policy decisions, candidate patch digest, changed paths, test results and state transitions.

### Git identity

Baseline, candidate and merge SHAs.

These prevent evidence from silently drifting to another revision.

## Test identity

The test runner writes JUnit. The controller records both aggregate counts and testcase identities.

A zero exit code with zero tests is not useful evidence.

## Event chain

Every event contains:

```json
{
  "seq": 4,
  "type": "candidate-created",
  "payload": {},
  "previous_hash": "...",
  "hash": "..."
}
```

`hash` is calculated from sequence, type, payload and previous hash.

Editing an old event invalidates the following chain.

## Pending effects

Crash recovery requires durable intent before a non-idempotent effect. The recovery scenario persists a merge request hash, reloads it after a simulated restart and refuses to invent a new identity.

## Evidence directory

Each demo run is self-contained:

```text
.demo/runs/<run-id>/evidence/
```

That directory is intentionally ignored by Git.
