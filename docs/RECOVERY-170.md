# Recovery and operations in 1.7.0

The supported persistence remains local JSON, immutable receipts, atomic replace/fsync
and one writer per run. An existing consumer retains its own authoritative
storage and controller. Neither adoption path requires an external database
or a distributed queue.

## Model dispatch and repeated cost

The shared `model_call_action` decision distinguishes a reusable receipt, a known
unstarted call and an indeterminate dispatched call. A request/effect ID is an
identity for recovery; it is not a provider guarantee of billing idempotency.

| Failure boundary | Behavior |
| --- | --- |
| Missing credentials or unavailable broker before preparation finishes | No model reservation/dispatch in the reference runtime; repair configuration and the next tick can proceed. |
| OS refuses to spawn the provider | Proven not dispatched. The operational reservation is released durably; consumers apply their documented core-compatible accounting. |
| Durable dispatch intent, then process crash/timeout/nonzero exit with no receipt | Do not call again automatically. The provider may have processed or charged the request. |
| Receipt durable, next state write/phase transition fails | Reuse the exact receipt without another provider call or another usage entry. Replay does not resolve credentials. |
| Strict JSON decoder rejects a completed reference-provider response | Record a bounded protocol error. Duplicate keys and nonfinite values remain invalid. A bounded repair is a new, counted attempt. |
| Operator explicitly retries a named unknown effect | Retain the old unknown reservation and allocate a new identity and budget reservation. Additional provider cost is possible. |

The dispatch intent necessarily precedes the process call. A crash in between can
produce a conservative unknown even when the provider did not run. Automatically
repeating it would make the opposite crash window unsafe. There is no claim of
exactly-once billing, cross-host deduplication, or control over retries internal to
an operator-supplied provider/Codex executable. The bundled HTTP adapter makes one
HTTP attempt and does not automatically follow redirects, retry, switch models or
switch billing identities. SDK/proxy retries in third-party adapters must be
reviewed separately.

The reference `retry-effect --binding EFFECT_ID` remains an explicit cost decision.
It refuses repetition when a receipt already exists. Source, policy, runtime,
run, attempt and request identities still bind every receipt. Never delete
receipts, edit pending state, reset counters, or change an epoch to bypass a hold.
Restoring an old backup while the original controller has progressed can also
repeat work: stop/fence the old controller and reconcile newer evidence before
resuming any restored snapshot.

## Initialization and observations

`initialization.json` binds a bootstrap to the product base, owner policy/goal,
runtime and run ID. The bare clone is created in a controller-owned staging area;
a completion marker precedes its promotion. `start` can finish its own interrupted
bootstrap, and `resume` can recover it when the first `state.json` write failed.
A changed authority/base or an unowned repository is rejected.

CLI and service status use one projection. Every successful save synchronizes
the task phase and publishes a monotonic revision and UTC update time. Read APIs
observe an atomically published snapshot without taking the writer lock. Usage
only follows receipt identities reachable from that snapshot; a durable pending
receipt may replace its unknown reservation, but later calls cannot enter it.

Approval and owner actions reacquire the writer lock and check the current decision
hash. A readable old snapshot grants no permission to act on newer evidence.
Owner audit rows include action ID, UTC time, reason, before/after status and exact
decision hash. `local-owner` identifies local authority, not a verified person.

## Installed provider adapter and doctor

`pip install .` installs `agent-reasoning-openai`, an optional command/v2 adapter
for the OpenAI Chat Completions API. Use `examples/operational/policy.openai.example.json`,
set absolute executable/product paths, select a model available to your account,
prepare the image and define real acceptance/test commands. The existing Codex
profile and custom command protocol remain supported.

The adapter reads only its explicit `OPENAI_API_KEY` credential target, supplied
through the configured environment reference or broker. It sends no tools, uses
one completion, sets an output-token bound, and passes the role's JSON schema in
the instructions. JSON object mode is used for transport portability; the
controller strictly validates the complete role contract before using the result.
Reported cached/input/output tokens are mapped without inventing absent counters.
See the [official API contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

`reasoning.check_argv` is a trusted, explicitly configured non-billing handshake.
Its stdin is `{"schema":"command-reasoning/check/v1","model":"..."}`. Success
must be exactly `{"schema":"command-reasoning/check/v1","ready":true,"protocol":2,"model_called":false}`
(protocol 1 for a legacy adapter). A custom adapter must implement this operation;
the controller never assumes that appending `--check` to an arbitrary program is safe.

`doctor` reports passed/failed/not_checked probes and exits 2 when a required
probe fails or the command adapter lacks a readiness handshake. The bundled
handshake checks local configuration and credential availability; it makes no
HTTP request and does not establish remote model access or available credit.
Codex readiness separately checks login status. Live model access remains
`not_checked`. GitHub governance and Git transport read access are separate probes;
readiness never claims that a push was tested. Configure Git SSH/credential helpers
for the service owner; the REST credential broker does not silently alter Git config.

## Local supervisor and review

```bash
agent-control serve --state /absolute/run --poll-seconds 5 --max-backoff 60
agent-control review --state /absolute/run
```

Set `AGENT_REVIEW_TOKEN` to a private printable token of at least 32 characters.
Review remains bound to loopback and a single OS owner. It displays phase, SHA,
risk, findings, verification evidence, exact-revision diff, usage and recent owner
actions. The complete decision JSON remains available. UI data uses text nodes;
source code and model findings do not become executable HTML.

RUNNING phases progress immediately. Temporary external waits and competing
writers use bounded backoff; paused/held states wait for owner action without
model polling. SIGTERM stops after the current bounded tick. `health.json` records
the beginning/end of the last tick and next polling delay; during a long tick the
started timestamp remains available. A separate supervisor lock prevents two
local supervisors, while every actual transition still uses the existing writer lock.

Use `examples/operations/agent-control.service` for continuous operation. Stop and
disable the older tick timer before enabling it. Review/edit owner, paths,
environment and stop timeout; retain the host's rootless Podman delegation setup.
The existing timer remains a supported alternative for an external scheduler.

## Checked backup and restore

```bash
agent-control pause --state /absolute/run --reason maintenance
agent-control backup --state /absolute/run --output /safe/run-backup.zip
agent-control restore --archive /safe/run-backup.zip --state /absolute/restored-run
agent-control status --state /absolute/restored-run
```

Export requires a paused run without pending effects or retirement. It includes
state, receipts, initialization identity and Git objects/config, with a checksummed
manifest. It refuses symlinks/special files and an existing output. Restore checks
paths, inventory, byte limits, hashes, usage accounting and Git object integrity,
and publishes only a validated paused directory. It never overwrites an existing run.
Treat the archive as private source/evidence; it is not an encrypted secret vault.

Before `continue`, fence the old controller and verify that no newer source of
execution evidence exists. Backup is not automatic HA or a controller transfer
protocol. A runtime mismatch still requires the explicit quiescent upgrade gate;
restore does not waive activation, authority or approval checks.

## Validation scope

Regression tests cover credential failure/restoration, unavailable broker, spawn
failure versus timeout, interrupted bootstrap, receipt replay, strict JSON errors,
concurrent observation, stale owner actions, supervisor backoff, backup/restore
and the adapter's request/usage/error contract. Tests use disposable Git products,
real local processes and controlled transports. A live paid model invocation,
your host's rootless container setup and deployment are separate evidence.
