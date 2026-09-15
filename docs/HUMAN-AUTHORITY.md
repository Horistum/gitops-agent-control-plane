# Human authority protocol

`NEEDS_DECISION` is a durable resumable authority boundary. It is not a pause-and-hope mechanism and it is not permission to merge whatever a mutable branch happens to contain later.

## What the human approves

A pending decision records:

- roadmap item and attempt;
- exact reviewed `candidate_sha`;
- candidate branch used as a mutable working reference;
- risk classification and reasons;
- allowed actions: `approve`, `reject`, `request_changes`.

The decision artifact also records the candidate SHA observed at decision time and whether that observation still matches the reviewed SHA.

## Approval is revision-bound

Immediately before `approve` can create a merge effect, the controller re-resolves `candidate_branch`. The current branch tip must equal all of:

1. the candidate SHA stored in durable state;
2. the SHA persisted in the pending human decision;
3. the reviewed candidate evidence SHA.

If the branch moved, disappeared, or resolves to another commit, approval fails closed with `BLOCKED_POLICY`. The `human-approve-after-tamper` conformance scenario moves the branch after review, adds a backdoor commit, and proves that the subsequent approval does not merge it.

## Merge semantics

The durable merge intent contains exact `base_sha` and `candidate_sha`. The runtime creates the merge from those commit objects, not from a branch name. Before advancing `main`, the local Git adapter requires current `main` to still equal the intended base and updates the ref with compare-and-swap semantics.

After creation, merge evidence verifies both parents:

- first parent equals the intended base SHA;
- second parent equals the approved candidate SHA.

The merge is therefore revision-bound at authorization, execution, and evidence consumption.

## Actions

### `approve`

Continue with the exact-SHA merge, post-merge verification, controller release-state transition, and goal reconciliation. A stale approval is rejected rather than reinterpreted.

### `reject`

Record the human decision, block the work item, delete the mutable candidate branch, and leave the retained candidate audit ref intact.

### `request_changes`

Convert the paused attempt into bounded repair feedback, discard the mutable candidate branch, and begin the next attempt only after recomputing baseline diagnostics, completed-item regression probes, and the acceptance negative control on the current `main` revision. Previous preconditions are never reused for a new base revision.

## Candidate retention

Every committed candidate receives a controller-created audit ref under `refs/tags/evidence/candidates/<run>/<item>/attempt-XX`. Candidate evidence records that ref. Deleting a transient candidate branch therefore does not make the reviewed commit unreachable or dependent on Git reflog retention.

## Production identity

The deterministic reference records `conformance-human`. A production adapter must bind the decision to an authenticated human identity and should preserve whatever organizational authorization evidence is required. Identity authentication is additional to, not a substitute for, exact revision binding.
