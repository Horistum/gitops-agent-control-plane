# Human authority protocol

`NEEDS_DECISION` is durable resumable state bound to an exact item and exact candidate Git revision.

Actions are `approve`, `reject`, and `request_changes`.

Before an `approve` action can create a merge effect, the controller re-resolves the durable `candidate_branch` and requires its current tip to equal the candidate SHA that was reviewed, recorded in candidate evidence, and persisted in the pending decision. If the branch moved, disappeared, or no longer resolves to that exact SHA, approval fails closed with `BLOCKED_POLICY`.

The merge effect then uses the exact candidate SHA, not the branch name. The local runtime creates the merge from exact base/candidate commits and advances `main` with a compare-and-swap ref update. Merge evidence records and checks both actual merge parents, so the approved candidate identity and the merged candidate identity cannot silently diverge.

`approve` resumes merge, post-merge verification, release-state transition, and reconciliation. `reject` terminates without merge. `request_changes` discards the candidate branch and routes the item into the next bounded attempt. Production adapters must additionally bind decisions to authenticated human identity; the deterministic fixture uses `conformance-human`.
