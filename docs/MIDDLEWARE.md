# Embed governance around an existing reasoning provider

Use the pure `control_plane_core` when the consumer already owns scheduling,
storage and effects. Use `agent_runtime` when the supplied Git/GitHub/Podman
controller matches the deployment. Do not run a second controller beside
FlowAI-Control: it already embeds the shared core and owns its own adapters.

These integrations preserve the separation between proposals, operator authority,
observed evidence and execution. Connecting an agent does not confer authority
on the agent's tool calls. A Claude, Copilot or proprietary adapter must return
structured proposals and allow the controller to own the effects. This release
does not ship vendor-specific CLI shims or automatically govern an existing
unrestricted agent session.

## Command reasoning

The primary example is `examples/operational/policy.example.json`. The existing
Codex/ChatGPT transport remains in `policy.codex.example.json`; its authentication
semantics and no-API-fallback rule are unchanged. An existing policy is never
silently migrated between providers or authentication methods.

An owner-installed adapter runs in a temporary empty working directory with a
small environment. It is trusted infrastructure with host process authority,
not an untrusted sandbox. Use absolute executable and script paths. Policy
arguments must not contain secrets. The operator installs and authenticates the
adapter; `doctor` checks its executable without making a model call or claiming
authentication succeeded.

With no `protocol` property, or `protocol: 1`, stdin remains
`{instructions,input,output_schema}` and stdout is the role result object. This
legacy protocol has no usage metadata. It remains covered by lifecycle tests.

With `protocol: 2`, the request also carries:

| Field | Meaning |
|---|---|
| `schema` | `command-reasoning/v2` |
| `model` | Operator-selected model string, including an intentionally empty provider default |
| `effect_id` | Stable controller effect identity; available to correlate provider calls |
| `output_schema` | Current role result contract |
| `response_schema` | Complete response envelope with the current role schema |

The controller persists the effect intent before invoking the adapter. The
adapter calls its chosen model/API, disables independent tool authority and
returns exactly one UTF-8 JSON document, without Markdown or log lines on stdout:

```json
{
  "schema": "command-reasoning/v2",
  "result": {
    "verdict": "ready", "summary": "Selected the eligible item", "risk": "low",
    "requested_files": [], "requested_searches": [], "requested_facts": [],
    "findings": [], "acceptance_evidence": [], "selected_item": "TASK-1"
  },
  "usage": {"input_tokens": 1200, "output_tokens": 200, "cached_input_tokens": 300},
  "provider": {"id": "company-model-gateway", "model": "configured-model", "request_id": "provider-request-123"}
}
```

This example is a discovery response; other phases use their advertised schema.
The controller validates every role result, including results from injected
in-process providers. Missing counters are unknown, not zero. `usage: {}` is
allowed. Counters are bounded nonnegative integers; cached input is a subset
of input, not an additional total. Provider metadata is adapter-reported and
must not contain credentials. No prices or monetary charges are inferred.

`effect_id` is a correlation key, not a promise that the external provider supports
idempotency. An unrecorded model outcome still requires explicit `retry-effect`.
A retry allocates another effect and consumes another reservation. A durable
response is reused after a controller crash. A role schema error preserves
well-formed v2 usage metadata; invalid metadata never becomes a zero-cost success.

Generated envelope schema: `schemas/command-reasoning-response.schema.json`.
The envelope's generic `result` object is additionally validated against the
phase-specific role schema at runtime.

## Credential references and broker contract

Secrets are resolved at use time. Policy, fingerprints and state contain only
references. For a command provider:

```json
"credentials": {
  "MODEL_API_KEY": {"kind": "env", "name": "AGENT_MODEL_API_KEY"}
}
```

The key is the child environment variable. The reference identifies the
controller-side environment source. Only declared credentials are copied into
the provider process. Reserved variables such as PATH, HOME, Python startup,
Git/SSH, Codex home, proxy settings and GitHub tokens cannot be injection targets.
Targets must be `API_KEY`, `TOKEN`, `SECRET`, or use `_API_KEY`, `_TOKEN`,
`_SECRET`, `_ACCESS_KEY_ID` or `_SECRET_ACCESS_KEY` suffixes; this excludes other
interpreter/loader configuration variables by default.
Product builds do not inherit this provider environment. An operator must never
deliberately map a GitHub credential into a model credential slot.

A broker reference delegates retrieval to an owner-controlled program:

```json
{
  "kind": "command",
  "argv": ["/opt/company/bin/credential-broker"],
  "reference": "tenant-a/model-production",
  "timeout": 10
}
```

The resolver executes the absolute program without a shell, in a temporary
directory with an isolated environment and bounded input/output/deadline. Stdin:

```json
{"schema":1,"reference":"tenant-a/model-production","purpose":"reasoning:MODEL_API_KEY"}
```

Success is exit 0 and exactly `{"value":"the-current-secret"}`. Values must be
nonempty, single-line and at most 16,384 characters. Output plus stderr is bounded
to 32,000 bytes. Invalid output, timeout, absence or a nonzero exit fails closed;
raw broker output is not included in public errors. The resolver does not cache
values, so a later call observes rotation. There is no automatic retry after an
authentication error that might have followed an external side effect.

The broker owns Vault/AWS/other client libraries, authentication, access policy
and secret lifecycle. Use its workload identity or an explicitly configured
protected file/socket. It cannot depend on arbitrary inherited controller
environment variables or the owner's HOME. A reference containing `tenant-a`
does **not** enforce tenancy: the deployment must authorize the requesting worker
and bind references server-side. No Vault or AWS SDK integration is bundled here.

For GitHub REST, add `publication.credential` using the same reference contract
and set `publication.token_env` to `""`. Existing `token_env` policies keep working.
The purpose is `github:OWNER/REPOSITORY`. A value is resolved for each request,
including pagination; previous credentials are not retained in controller state.
**Git clone/fetch/push authentication is separate.** Configure its credential
helper/SSH identity in the owner boundary; the REST broker does not configure Git.

The trusted adapter/broker can itself read host files or emit sensitive output.
Environment minimization does not sandbox it. Do not run tenant-supplied broker
programs or provider executables on a shared controller host.

## One-step workers

```python
from agent_runtime.service import RunService

# Resolve this path from trusted deployment configuration, not request JSON.
run = RunService("/var/lib/agent-control/approved-run")
outcome = run.tick()
if outcome["outcome"] == "busy":
    # A supervisor/queue can schedule the same run again later.
    pass
else:
    status = outcome["state"]["status"]
```

`tick()` performs at most one phase/effect dispatch and returns the existing
controller summary. A phase may include a bounded model or build call, so execute
it in a worker process, not an HTTP event handler. `status()`, `decision()` and
`usage()` read a consistent snapshot under the same writer lock. Contention is
an explicit `Busy` error for those reads; only `tick()` converts it into a
retryable outcome. Worker payloads must never select arbitrary run paths,
credentials, policy or approval identities.

Duplicate work notifications are safe under the existing single-host lock and
effect reconciliation rules. They are not an exactly-once transport. A crash
during a model call stops for explicit uncertainty handling, rather than letting
the queue blindly spend another call. Completed/held/paused runs spend no new
model calls. The durable run state is authoritative; notifications only wake it.

CLI equivalent: `agent-control tick --state RUN`. Exit 0 means that the command
reported an outcome (including busy/held); inspect JSON for completion. The
existing `start`/`resume` exit codes are unchanged. The example systemd timer in
`examples/operations` is a **single-host** supervisor, not a distributed queue,
webhook receiver or scheduler with tenant fairness.

### Several runs

An owner running more than one goal keeps one run directory per goal, as
before; `agent_runtime/registry.py` only adds a read-only status view across
them, never a shared store or a second writer.

```bash
agent-control registry --root /var/lib/agent-control/runs
```

`--root` is either one run directly, or a flat directory whose immediate
subdirectories are runs (a natural layout for a supervisor that already
iterates that same directory). Discovery does not recurse and does not follow
symlinked children, and is bounded to 512 runs. Each run's existing
`status()` projection is read without taking its writer lock, exactly as
`agent-control status` already does for one run; a run whose `state.json` is
missing or unreadable is reported as `"readable": false` with a reason,
never allowed to hide or crash the rest of the report. This is a status view,
not a control plane: pause, approve and the other owner actions still operate
on one `--state RUN` at a time.

## Local decision review

```bash
agent-control decision --state /absolute/run > human-decision.json
# Generate once in the controller shell; securely copy its value to the local UI.
export AGENT_REVIEW_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
agent-control review --state /absolute/run --port 8765
```

Open `http://127.0.0.1:8765` and enter that token. The server never prints the token
or embeds it in a URL, page, access log or browser storage. For a remote owner
host, use an authenticated SSH tunnel and the same loopback URL. Do not expose
the server with a public reverse proxy; it is not an enterprise authentication
boundary and has no TLS termination, SSO, RBAC or named reviewer identities.

The UI displays the same `human-decision.json` projection as `decision`, including
head/base SHA, specification/policy/runtime hashes, risk, role findings, feedback,
PR identity and verification evidence. Untrusted strings render as text. The
document is derived from authoritative state, not maintained as a second ledger.
An exported file is a snapshot and never an approval authority source.

Approval sends both the exact candidate binding and the fingerprint of the full
displayed document. Under the writer lock the controller reloads state, recomputes
the candidate identity and rejects changed decisions. CLI owners can request the
same full-document protection with `approve --binding HASH --decision-hash HASH`.
The legacy binding-only CLI remains supported and now also recomputes identity.
The approval records both hashes with local-owner authority. This is not proof
of a named compliance officer's identity. Approval does not call a model, advance
the worker or bypass existing merge/CI/base-movement checks.

The server accepts only the exact loopback Host, requires a bearer token for
decision/approval APIs, rejects cross-origin requests, limits request bodies and
disables caching. There are no arbitrary filesystem or command endpoints.

## Operational usage

`agent-control usage --state RUN` derives a report from validated immutable
receipt identities plus current/abandoned pending intents. It includes:

- lifetime reserved attempts (`model_calls`), recorded results and unknown outcomes;
- schema-invalid recorded results, separate from successful structured results;
- per-effect provider metadata and reported counters, without prompt/source bodies;
- token totals and per-counter observation counts, so missing usage is visible.

A receipt written just before a crash is counted once even before state consumes
it. An explicit retry keeps the abandoned unknown attempt alongside the new one.
Missing/corrupt receipts or inconsistent reservation counts fail the report;
they do not silently reduce the bill. Runtime upgrades retain historical receipts.

These hashes detect inconsistency, not malicious replacement by the storage
owner. Provider-reported usage is not authenticated billing evidence. Invoicing
still needs trusted provider usage reconciliation, durable append-only events,
pricing/version/currency rules, retention, corrections and unknown-outcome policy.
The report explicitly returns `billing_ready: false`.
