# Human authority protocol

`NEEDS_DECISION` is durable resumable state bound to an exact item/candidate.

Actions are `approve`, `reject`, and `request_changes`.

`approve` resumes merge, post-merge verification, release-state transition, and reconciliation. `reject` terminates without merge. `request_changes` discards the candidate branch and routes the item into the next bounded repair attempt. Production adapters must bind decisions to authenticated human identity; the fixture uses `human-fixture`.
