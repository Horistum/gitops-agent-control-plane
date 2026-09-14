# Operations

## Normal operating states

The portable state vocabulary is `RUNNING`, `WAITING_EXTERNAL`, `NEEDS_DECISION`, `BLOCKED_POLICY`, `FAILED`, `PAUSED` and `IDLE`.

The current backend may use additional internal phase names. Operator-facing tooling should map them to this stable vocabulary.

## Owner control surface

Use `scripts/control.py`, which currently supports:

```text
refresh
pause
drain
resume
activate --fingerprint HASH
retry --task ID
approve --task ID --hash HASH
replan --task ID --hash HASH
cancel-goal --goal ID --hash HASH
```

The wrapper exists so backend command syntax can change without rewriting operational documentation.

## Safe pause vs drain

`pause` prevents further progress at the next controller boundary. It does not invent a successful outcome for a pending operation.

`drain` allows an active task to reach its verified terminal boundary and then pauses before selecting another task. Prefer drain for planned maintenance and upgrades.

## Runtime/config changes

Changing policy, runtime code, trusted role instructions or model binding changes runtime identity. The controller must pause and require fresh explicit activation so evidence from an older execution epoch cannot satisfy a newly configured system.

## Failure handling

Use `retry` only for genuinely retryable infrastructure/transient failures. Retry must not bypass a risk decision.

Use `replan` when the current plan/candidate should be discarded and fresh planning is required. Replan invalidates candidate-level evidence rather than pretending old tests/reviews apply to the new plan.

Use `cancel-goal` to end the exact active goal when its product pull request is still safely cancellable.

## Observability

The current adapter stores local health/log data under:

```text
~/.local/state/agent-control-plane/
```

Typical diagnostics:

```bash
systemctl --user status agent-control-plane --no-pager
journalctl --user -u agent-control-plane -n 200 --no-pager
```

Backend-specific low-level diagnostics may exist, but normal operation should use the generic control surface and control-center issue.

## Host transfer

A planned transfer requires drain/pause, no active task or pending effect, old writer stopped, explicit writer identity transfer, new-host verification and fresh activation.

Never run two hosts under the same single-writer identity.

## Upgrades

Upgrades are owner-operated trust-boundary changes, not ordinary product tasks. A new adapter/runtime version must be pinned, reviewed, verified against this reference contract and installed only at a safe state boundary. Compatibility changes belong in `COMPATIBILITY.json` and adapter-specific code.
