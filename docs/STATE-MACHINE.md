# State machine

The standalone runtime exposes the control-flow states that matter to a bounded autonomous delivery system.

```text
INITIALIZING
    |
    v
DISCOVERY
    |
    v
PLANNING
    |
    v
PROPOSAL
    |
    +------ unauthorized ------> BLOCKED_POLICY
    |
    v
CANDIDATE
    |
    +------ tests fail --------> FAILED_VERIFICATION
    |
    v
REVIEWED
    |
    +------ risk boundary -----> NEEDS_DECISION
    |
    v
MERGING
    |
    v
POSTMERGE
    |
    +------ verification fail -> FAILED_VERIFICATION
    |
    v
COMPLETED
```

The demo currently records a compact state object rather than every transient label, while the event log preserves the detailed transition history.

## Terminal states

### `COMPLETED`

A merge identity exists and post-merge executable evidence is green.

### `BLOCKED_POLICY`

The requested/proposed action exceeded authority. No later evidence can retroactively authorize that candidate.

### `FAILED_VERIFICATION`

The change was within authority but executable evidence failed.

### `NEEDS_DECISION`

Automation reached an explicit human authority boundary. This is not a failure and not permission to continue.

## Recovery identity

A pending external effect carries a request hash. Recovery continues only when durable state, effect intent and candidate identity agree.
