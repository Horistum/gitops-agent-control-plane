# Writing a command reasoning adapter

This is the reference contract for authors implementing a `reasoning.kind=command`
adapter, distilled from [middleware integration](MIDDLEWARE.md) into a single
checklist and a naming registry. It does not restate that document's full
protocol description; read it first. This file exists so that a second, third
and tenth adapter converge on the same conventions instead of each inventing
its own environment names and handshake behavior.

## What an adapter owns

An adapter is trusted infrastructure the operator installs and authenticates.
It owns exactly:

1. reading one JSON request from stdin;
2. calling its own model/API using its own authentication;
3. writing exactly one JSON response to stdout, and nothing else;
4. implementing the `--check`-style readiness handshake (below).

It does not own execution, merge, approval, risk, path or budget decisions.
Returning a structured proposal never confers effect authority on the adapter,
the model it calls, or any tool that model believes it invoked. An adapter
that lets its model run shell commands, edit files or call external tools
before returning its response is out of contract: the controller's isolation
assumptions (empty working directory, bounded stdin/stdout, no ambient
credentials beyond declared targets) depend on the adapter making one bounded
call, not proxying an open-ended agent session.

## Protocol version

Default (absent `protocol`, or `protocol: 1`): stdin is
`{instructions, input, output_schema}`; stdout is the bare role result object.

`protocol: 2`: stdin adds `schema`, `model`, `effect_id`, `response_schema`.
Stdout is the complete envelope:

```json
{"schema": "command-reasoning/v2", "result": {...}, "usage": {...}, "provider": {...}}
```

`usage` fields are `input_tokens`, `output_tokens`, `cached_input_tokens`
(bounded nonnegative integers; `cached_input_tokens` cannot exceed
`input_tokens`); omit a counter you cannot observe rather than reporting zero.
`provider` is `{id, model, request_id}`, all adapter-reported strings with no
credentials. New adapters should default to `protocol: 2`: it is the only
version that carries usage into `agent-control usage` and the review UI.

## Readiness handshake

`doctor` and `Reasoning.preflight(readiness=True)` invoke `check_argv` (falling
back to `argv` for a legacy adapter with no separate check command) with:

```json
{"schema": "command-reasoning/check/v1", "model": "configured-model"}
```

The adapter must exit 0 and print exactly one line:

```json
{"schema": "command-reasoning/check/v1", "ready": true, "protocol": 2, "model_called": false}
```

`protocol` matches the adapter's advertised protocol version. This handshake
must not call the model, spend quota, or make a network request beyond what
local credential validation requires. It proves local configuration is usable,
not that a live call would succeed; `doctor` reports live model access as
`not_checked` on purpose. Do not assume that appending `--check` to an
arbitrary unmodified executable is safe — implement the handshake explicitly.

## Credential target naming

Declare credentials under `policy.reasoning.credentials` as
`{TARGET_ENV_NAME: {reference}}`. `agent_runtime/credentials.py` enforces a
positive allowlist, not a blocklist: a target must be exactly `API_KEY`,
`TOKEN`, or `SECRET`, or end with `_API_KEY`, `_TOKEN`, `_SECRET`,
`_ACCESS_KEY_ID`, or `_SECRET_ACCESS_KEY`, and must not start with
`GIT_`, `SSH_`, `CODEX_`, `PYTHON`, `LD_`, or `DYLD_`. This is deliberately
strict: it blocks interpreter, loader and transport-hijacking names by
construction, not by enumerating them.

Pick a target name that is specific to your provider, not generic, so two
adapters configured in the same policy cannot collide. Register it here when
you add a bundled adapter:

| Adapter | Bundled at | Target name | Notes |
|---|---|---|---|
| Codex CLI | `reasoning.kind=codex` (separate transport, not `command`) | n/a | Authenticates via `codex_home`, not a credential reference |
| OpenAI Chat Completions | `agent_runtime/openai_adapter.py` (`agent-reasoning-openai`) | `OPENAI_API_KEY` | Reads only this target from its environment; see `examples/operational/policy.openai.example.json` |

A custom, non-bundled adapter does not need an entry here, but should still
pick a target name that would not collide with this table (for example
`ANTHROPIC_API_KEY`, `COMPANY_MODEL_TOKEN`) so a policy can name more than one
provider without ambiguity, and so a future bundled adapter for that provider
can adopt the same name your deployments already use.

## Transport and error behavior

- Endpoint, if your adapter talks HTTP: require an explicit `https://` URL with
  no embedded credentials, query or fragment; disable automatic redirects;
  disable proxy auto-detection unless the operator configured one explicitly.
- Make one attempt. Do not retry, fail over to another model, or switch billing
  identity inside the adapter — the controller's dispatch/receipt boundary
  already governs retry, and a hidden adapter-level retry defeats its
  uncertain-outcome accounting.
- On any failure (transport, malformed upstream response, refusal), exit
  nonzero and print a short diagnostic to stderr **without echoing the
  request, the response body, or any resolved credential value**. The
  controller records that the call did not produce a usable result; it does
  not need — and must not receive — raw provider output in its persisted state.
- A finished-but-unusable upstream answer (refusal, truncation, tool call
  instead of content) should still make your adapter exit 0 with `result: {}`
  and whatever `usage`/`provider` you can report. The controller's bounded
  protocol-repair path handles an empty or schema-invalid `result`; it cannot
  distinguish "no answer" from "adapter crashed" unless you exit nonzero only
  for the latter.
- Never write partial JSON, log lines, or trailing text to stdout. Stdout is
  parsed as exactly one JSON document.
- If your provider supports prefix-based prompt caching, serialize `input`
  with the run/item-stable fields (`goal`, `authority`, `criteria`, `sources`)
  first and the call-volatile fields (`task`, `phase`, `memory`,
  `omitted_paths`) last, instead of an alphabetical or insertion-order dump.
  Key order carries no meaning to the controller or to a JSON parser; nothing
  here hashes or compares this specific string. It only changes how much of
  the prompt a caching-aware provider can reuse across the several role calls
  a single item typically makes. `agent_runtime/openai_adapter.py`'s
  `cache_friendly_json()` is a reusable reference implementation of this.

## Self-certifying an adapter

`scripts/verify_adapter.py` drives a configured command adapter through the
readiness handshake and a synthetic request for each role, and validates the
response against the same schemas the controller enforces
(`schemas/command-reasoning-response.schema.json` plus the role's own schema).
Run it against your adapter before wiring it into a real policy:

```bash
python3 scripts/verify_adapter.py --policy /absolute/policy.json
```

It never spends a real model call unless your adapter's own logic does so
when answering a synthetic request; inspect your adapter's behavior under
test before pointing it at a paid account. A pass is evidence of protocol
conformance, not of reasoning quality or production readiness — see
[verification and limits](VERIFICATION.md) for what a passing gate does and
does not establish.
