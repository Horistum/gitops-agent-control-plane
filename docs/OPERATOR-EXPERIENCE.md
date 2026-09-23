# Understand a run

Start with one read-only command:

```bash
agent-control explain --state /absolute/agent-runs/my-goal
```

It combines the current decision, diagnostic cause, conditional recovery commands,
receipt presence, model usage, recent transitions and diagnostic events. Each
suggested command includes the actual run path and any required exact binding.
It does not call a model, acquire the writer lock, update state, fetch Git remotes
or execute recovery commands.

For scripting, use `explain --format json`. The default is readable text;
`--format table` is an alias for that text. `--limit N` bounds recent entries to
1..100 (default 10). Existing commands keep their JSON default:

```bash
agent-control status --state /absolute/agent-runs/my-goal --format table
agent-control decision --state /absolute/agent-runs/my-goal --format table
agent-control status --state /absolute/agent-runs/my-goal --format json
```

An explanation is an observation, not permission. Conditions accompany the
suggested step. An uncertain model call without a receipt never defaults to a
paid retry. Receipt presence alone is not validity: reconciliation validates the
exact request and execution frame. A full budget cannot be reset by retry/replan.

Logs, local ref observations and presentation text remain outside the existing
decision hash. The controller still revalidates state, runtime, authority,
receipts, evidence and candidate identity when acting. Reload an old view before
making a decision.

## Which command means what?

| Need | Command | Effect |
|---|---|---|
| Understand a stop | explain | Combined read-only explanation and conditional next step |
| Check progress and locate the result | status | Read-only summary and local repository identity |
| Review candidate and evidence | decision | Exact decision; does not approve anything |
| Approve the displayed candidate | approve --binding ... --decision-hash ... | Authorizes only the matching candidate and decision |
| Advance once / drive until stopped | tick / resume | Executes ready work; does not clear a hold or pause |
| Remove a pause | continue | Unpauses; a blocked hold still needs its own recovery |
| Retry a held, retryable task | retry | Resumes the held phase after its cause is fixed |
| Recover a pending non-model effect | reconcile | Resumes a replay-safe effect; follow with a tick |
| Recover a pending model result | reconcile-effect --binding ... | Requires the original receipt; no replacement call |
| Explicitly replace an uncertain model call | retry-effect --binding ... | May incur duplicate cost; retains the lifetime budget |
| Retire an attempt and plan again | replan | Requires cleared pending effects and remaining authority/budget |
| Accept changed runtime bytes | pause, then upgrade | Requires a quiescent boundary; eligible unchanged held attempts can require explicit --suspend |

Each command's `--help` explains its scope. Existing names remain supported.

## Where did my change go?

`status.product` names both locations:

| Field | Meaning |
|---|---|
| source_checkout | Original policy product path; this checkout is unchanged |
| repository | Absolute path of this run's product.git |
| base_ref | Exact refs/heads/&lt;base_branch&gt; inside product.git |
| base_ref_sha | Current local ref observation, distinct from the candidate head |
| inspection_error | Why the ref could not be read, without hiding the rest of the status |

Top-level `head` identifies the candidate or observed discovery/base.
`merge_sha` identifies the active or latest archived merge. In local publication,
the verified merged result lives in `product.git`. With GitHub publication, the
local ref is the controller's local observation; this read does not check the
current remote. For example, using the repository path and base ref from the report:

```bash
git --git-dir /absolute/agent-runs/my-goal/product.git show refs/heads/main:app.py
```

Before a run starts, `doctor` checks policy dependencies; it has no run-owned
repository to inspect.

## Local review UI

`agent-control review --state RUN` uses the same explanation via authenticated
`GET /api/explain`. It presents the situation, conditional next command, failure
cause, result locations, route, recent transitions, owner actions, review findings,
verification summaries and diagnostic history. Technical details and the complete
decision JSON remain available in closed disclosures.

The route comes from the actual reducer and shows risk, adaptive, critical and
challenge modifiers. It is not a percentage complete: repairs and risk escalation
can revisit phases. Older transitions have no timestamps and bounded history can
omit early entries. The UI does not invent times or infer that earlier phases
have completed. Past diagnostic events are explicitly marked as history.

The token, loopback host/origin checks, exact decision validation and explicit
duplicate-cost acknowledgement remain enforced. Changing the token or action
while a read is loading cannot enable buttons from a stale response.

## State layout, without hand-editing it

`state.json` is the authoritative snapshot, not an operator input format. Its
64 MB reader limit is a maximum accepted file size, not a normal allocation.
Use the projections above to inspect it and owner commands to change it.
This table documents the main groups, not a new writable schema:

| Group | Representative keys | Purpose |
|---|---|---|
| Identity | schema, run_id, revision, updated_at | Identify the snapshot and revision |
| Frozen authority | policy, goal, policy_hash, runtime_hash | Bind authorized inputs and executable bytes |
| Current activity | status, phase, paused, base, task, discovery | Active candidate or work selection |
| Durable effects | pending, receipts, effect_epoch, abandoned_effects | Crash recovery and uncertain-call handling |
| Lifetime accounting | model_calls | Reservations, including uncertain outcomes |
| Goal evidence | completed, criteria, cli_cases, projection | Observed obligations and eligible work |
| Attempts and recovery | archive, attempts, owner_replans, owner_intent, carried_tests, carried_risks | Preserve attempts, bounds and accepted evidence |
| Explanation and history | reason, diagnostic, history, human_actions | Current cause, bounded transitions and owner audit |

A task holds item/attempt, phase/resume_phase, head/base/spec_hash, risk,
completed_phases, proposals, verification observations, reviews, approval and PR
identity. The decision projection exposes the review-relevant subset.

| Adjacent path | Role |
|---|---|
| product.git/ | Product objects and run-owned refs |
| receipts/&lt;effect-id&gt;.json | Durable exact-request outcomes for replay |
| diagnostics.jsonl and .1 | Bounded, rotated explanation history; never authority |
| health.json | Supervisor liveness observation |

An exported `human-decision.json` is a review projection, not current authority.
One state snapshot is read atomically. Git refs, receipts and logs are separate
observations and can change during the read. An unavailable log, usage receipt or
repository is labelled explicitly without concealing the rest of the explanation.

See the [generated workflow map](WORKFLOW.md) and
[failure diagnostics and upgrade recovery](RECOVERY-183.md).
