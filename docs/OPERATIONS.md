# Operations

## Control Center versus state

The command issue is where an owner sees status and sends commands. The authoritative execution
state is the `loop-state` Git branch.

The state branch contains:

- `state.json`: current snapshot;
- `events/NNNNNNNN.json`: hash-linked transition receipts;
- `runs/*.json`: immutable external-effect receipts;
- `reports/*.md`: task reports;
- `DASHBOARD.md`: human-readable state projection.

Never repair a stuck task by hand-editing these files and force-pushing the branch.

## Runtime states

Operator-facing states include:

- `RUNNING`;
- `WAITING_EXTERNAL`;
- `NEEDS_DECISION`;
- `BLOCKED_POLICY`;
- `FAILED`;
- `PAUSED`;
- `IDLE`.

The controller can wait on CI, quota/cooldown or an external PR without that being a failed task.

## Owner commands

Use only exact commands displayed by the current control center. Core commands include:

```text
/loop pause
/loop drain
/loop refresh
/loop resume
/loop activate <fingerprint>
/loop retry <TASK>
/loop replan <TASK> <approval-hash>
/loop approve <TASK> <approval-hash>
/loop cancel-goal <GOAL> <goal-hash>
```

A valid command is:

- authored by an authorized owner user;
- a new comment;
- unedited;
- one line;
- not replayed.

Commands never waive hard safety gates.

## Pause versus drain

`pause` is immediate emergency stop behavior.

`drain` lets the active task reach a verified terminal boundary and then pauses before selecting new
work. Prefer drain for planned maintenance/upgrades.

## Policy/runtime changes

Policy fingerprint includes configuration and trusted runtime/role hashes. A runtime/configuration
change requires restart and explicit reactivation.

Do not “preserve” an old activation across changed authority. The new fingerprint is precisely the
point.

## Logs

Default reference locations:

```text
~/.local/state/flow-loop/health.json
~/.local/state/flow-loop/logs/
journalctl --user -u flow-loop
```

Model raw output is intentionally not dumped into Git. Durable receipts carry bounded structured
evidence instead.

## Recovery principles

1. stop competing writers before recovery;
2. inspect remote `loop-state` first;
3. do not equate network failure with missing state;
4. do not delete/recreate state after an ambiguous push;
5. reconcile exact PR/SHA/check state before repeating an external effect;
6. transfer controller identity only at an idle, paused boundary;
7. never run two hosts with the same `controller_id` against one state branch.

## Quota

ChatGPT/Codex quota exhaustion becomes `quota_wait` and configured cooldown. It must not trigger API
billing fallback.

## Upgrades

The reference v1 installer is for the exact compatible commit in `COMPATIBILITY.json`.

FlowAI-Control 0.3.0's upstream `upgrade_v030.py` was built around the original pilot where the
controller source repository and control/state repository were the same. Do not point it at a
tenant-separated control repo and assume provenance will work.

A future compatible reference revision should update `COMPATIBILITY.json`, validate the new runtime,
drain the old service and install the new immutable runtime with an explicit new fingerprint.
