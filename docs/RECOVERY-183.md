# 1.8.3: diagnosable failures and pause after runtime drift

## Read the cause before choosing a recovery action

```bash
agent-control status --state /absolute/run
agent-control decision --state /absolute/run
agent-control diagnostics --state /absolute/run --limit 20
```

Status and decision add a `diagnostic` object when a failure, protocol repair or
runtime/authority mismatch is observed. CLI errors use the same object on
stderr. It includes:

- `id`, `at`, `code`, and the specific `message`;
- the operation, phase, run, item, revision at observation and source head;
- the exact pending effect ID and kind, if any;
- exception types, causal chain, and stack file/function/line locations;
- bounded details such as executable, exit code, HTTP status and provider request ID;
- suggested `next_steps`, subject to the existing authority and recovery gates.

Known boundaries have stable codes (for example `RUNTIME_CHANGED`,
`DISCOVERY_NOT_SELECTED`, `MODEL_BUDGET_EXHAUSTED`, and
`REASONING_EXECUTABLE_UNAVAILABLE`). Unclassified controller exceptions become
`UNEXPECTED_ERROR`, retaining their message and location. No exhaustive list of
failure causes is required. Unknown tick failures hold the run; a restart does
not silently dispatch the unfinished operation again. Process termination and
crash signals outside `Exception` retain their existing receipt recovery behavior.

A bounded protocol repair is visible immediately even while status is RUNNING.
The current diagnostic clears after progress or an explicit recovery action;
the historical log remains available. Missing credentials and unavailable
executables before dispatch do not consume a model-call reservation.

Read-only inspection also detects runtime drift before constructing a controller.
Its diagnostic has `operation=observe`, a stable ID, and `at=null` because the
time the drift first happened is unknown. It does not change state or append to
the log. After drift, the decision offers only `pause` (until paused); it does
not offer actions that require the old executable identity.

## Logs and the local review UI

Run failures are recorded in `<run>/diagnostics.jsonl`, rotated at approximately
1 MB with one previous file. Files use owner-only permissions. A logging failure
leaves the original diagnostic visible with `log_written=false`; logging never
turns a failed operation into success. CLI `diagnostics` and authenticated
`GET /api/diagnostics` expose up to 100 recent events. Historical logs are
diagnostic information, not execution receipts or approval evidence.

The review UI shows **What happened** before the candidate details: the specific
message, code, phase, operation, diagnostic ID and next steps. Stack locations
and technical details are expandable. Failed UI actions retain their concrete
error instead of replacing it with a generic reload message. The same ID joins
the UI error to its log entry. Existing token, origin and exact-decision checks
remain required.

Reports omit stack locals, source lines, request bodies and authentication
headers. Known credential values and common secret patterns are redacted from
messages and bounded subprocess stderr excerpts. Provider diagnostics and
stderr remain untrusted text; the UI uses text nodes, and no diagnostic grants
authority or is interpreted as successful evidence. Review log content before
sharing: arbitrary third-party stderr may contain private application data.

Bundled Anthropic and OpenAI adapters emit bounded `provider-error/v1` JSON on
stderr for failure. Selected HTTP error fields (status, error type/message and
request ID) survive the command boundary. The runtime also supports a bounded
stderr excerpt for other command adapters. No automatic provider retry or
billing fallback is added. Doctor identifies the specific failing probe and
its cause without calling a model.

## Recover when the runtime was already changed

Install the reviewed 1.8.3 controller, then inspect and pause the same run:

```bash
agent-control decision --state /absolute/run
agent-control pause --state /absolute/run --reason 'Prepare reviewed runtime upgrade'
agent-control upgrade --state /absolute/run
```

Pause is audited and holds the writer lock. It still rejects changed policy or
goal authority and stale UI decisions. It changes neither the original runtime
hash, model budget, effect epoch nor pending effects. Upgrade still requires a
quiescent boundary and validates the saved authority. It cannot cross a pending
effect or owner intent; an active task requires the existing narrowly eligible
`--suspend` path. If a pending effect needs the original runtime for
reconciliation, restore that exact runtime first.

After a successful upgrade, inspect the decision again. For a discovery hold
with no selected task and budget remaining, an explicit `replan --reason ...`
can start another discovery. Use `continue` to release the pause and `tick` to
observe one step. An upgrade alone does not clear a policy hold, and replanning
does not reset the lifetime model budget. Do not rewrite state hashes, receipts
or authorization to force a continuation.
