# 1.8: receipt recovery and prompt efficiency

The supported deployment remains single-host JSON state with per-run flock.
Flow retains Git-backed state. No database service or migration is required.
Upgrade at a quiescent boundary using the existing reviewed upgrade procedure;
runtime identity remains part of effect authority.

## Recover a restored model receipt

A call whose response was lost stays blocked: tick, restart and continue must not
silently pay for it again. If the original valid receipt has been recovered:

```bash
agent-control reconcile-effect --state /absolute/run --binding EXACT_PENDING_EFFECT_ID
agent-control tick --state /absolute/run
```

Use `agent-control reconcile-effect --help` for the installed argument form.
The owner action checks receipt integrity, exact request identity, policy/runtime,
epoch, task attempt, phase and unchanged task frame. It reverses only fields
written by the hold. The next normal tick validates the entire reconstructed
request and consumes its original receipt. It does not reserve another call,
advance the effect epoch or prepare/dispatch a provider request. The review API
uses the current decision hash as well as the exact pending effect binding.

A missing/invalid receipt remains blocked. `retry-effect` explicitly permits a
new paid attempt when evidence is unavailable; it cannot replay over an existing
receipt. This is conservative recovery, not a guarantee of exactly-once billing
by an external provider.

## Operational corrections

- Registry isolates corrupt non-object state/task/archive entries per run and
  surfaces initialized runs whose state file disappeared.
- Packaged `agent-verify-adapter` requires an explicit readiness handshake, gives
  real probes valid identities and returns structured failures. See ADAPTERS.md.
- Shared core 1.8 exports bounded usage validation and lossless prompt helpers.
  The paired Flow 0.9 consumer preserves missing usage as unknown and records
  counter observation counts, including unclassified legacy aggregates.

## Reproducible prompt measurements

Run `python3 scripts/benchmark_prompts.py` from this checkout. It drives the real
controller through disposable Git/test subprocesses with a controlled reasoning
peer, captures all 10 phase payloads and renders each identical input through the
1.7 and 1.8 prompt layouts. No model or external API is called.

One local fixture run measured:

| Surface | Before | After | Reduction |
|---|---:|---:|---:|
| Codex stdin, UTF-8 bytes | 58,535 | 41,193 | 29.6% |
| Serialized HTTP messages, UTF-8 bytes | 66,094 | 65,554 | 0.8% |

Codex receives the full schema once via `--output-schema`; its redundant stdin
copy is removed. The Codex row measures **stdin only**, not the provider's full
internal model context (which still includes the schema). HTTP messages retain
all task data and use a shared prefix before role-specific instructions. Schemas
in prompt text omit only semantically redundant zero-length lower bounds;
validation still uses the original schemas.

These are byte/layout measurements, not token counts, cache-hit rates, credits
or demonstrated reasoning quality. Git fixture identities can vary between runs.
Provider cache effectiveness must be measured using returned cached-token usage
on the actual selected model. No acceptance evidence, hashes, role independence,
policy or execution gates are removed to reduce prompts.
