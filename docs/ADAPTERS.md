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

`doctor` and `Reasoning.preflight(readiness=True)` invoke an explicitly configured `check_argv` with:

```json
{"schema": "command-reasoning/check/v1", "model": "configured-model"}
```

The adapter must exit 0 and print exactly one line:

```json
{"schema": "command-reasoning/check/v1", "ready": true, "protocol": 2, "model_called": false}
```

Without `check_argv`, readiness reports `adapter: not_checked`; it never invokes
the normal inference command as a fallback. Certification then fails.

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
| Anthropic Messages | `agent_runtime/anthropic_adapter.py` (`agent-reasoning-anthropic`) | `ANTHROPIC_API_KEY` | Reads only this target; see `examples/operational/policy.anthropic.example.json` and the caching note below |

A custom, non-bundled adapter does not need an entry here, but should still
pick a target name that would not collide with this table (for example
`COMPANY_MODEL_TOKEN`) so a policy can name more than one provider without
ambiguity, and so a future bundled adapter for that provider can adopt the
same name your deployments already use.

## Transport and error behavior

- Endpoint, if your adapter talks HTTP: require an explicit `https://` URL with
  no embedded credentials, query or fragment; disable automatic redirects;
  disable proxy auto-detection unless the operator configured one explicitly.
- Make one attempt. Do not retry, fail over to another model, or switch billing
  identity inside the adapter — the controller's dispatch/receipt boundary
  already governs retry, and a hidden adapter-level retry defeats its
  uncertain-outcome accounting.
- On a transport failure or an unreadable upstream response, exit
  nonzero and print a short diagnostic to stderr **without echoing the
  request, the response body, or any resolved credential value**. The
  controller records that the call did not produce a usable result; it does
  not need — and must not receive — raw provider output in its persisted state.
  Bundled adapters emit `provider-error/v1` JSON with a bounded message and
  selected HTTP status/error/request-ID fields. Version 1.8.3 preserves these
  details in the run diagnostic and UI; other adapters receive a bounded,
  redacted stderr excerpt. These are explanations, never execution evidence.
  See [failure diagnostics](RECOVERY-183.md).
- A finished-but-unusable upstream answer (refusal, truncation, tool call
  instead of content) should still make your adapter exit 0 with `result: {}`
  and whatever `usage`/`provider` you can report. The controller's bounded
  protocol-repair path handles an empty or schema-invalid `result`; it cannot
  distinguish "no answer" from "adapter crashed" unless you exit nonzero only
  for the latter.
- Never write partial JSON, log lines, or trailing text to stdout. Stdout is
  parsed as exactly one JSON document.
- The bundled HTTP adapter sends shared instructions first, stable input fields
  (`goal`, `authority`, `criteria`, `sources`) as user data next, then trusted
  role/schema instructions and volatile user data. External producers with custom
  instructions retain the two-message form. Source data never becomes a system
  message. `stable_prompt_json` orders keys without dropping fields;
  `compact_prompt_schema` removes only redundant zero-length lower bounds from
  prompt copies. Original validators and Codex `--output-schema` stay unchanged.
  Actual provider caching depends on its rendered prefix, model and eligibility;
  message ordering alone does not establish a cache hit or monetary saving.
  See [measured prompt fixtures](RECOVERY-180.md).
- Providers differ in how caching is invoked. The bundled OpenAI adapter relies
  on that provider's automatic prefix matching; ordering alone is enough. The
  bundled Anthropic adapter instead marks explicit `cache_control: {"type":
  "ephemeral"}` breakpoints (`agent_runtime/prompts.py:anthropic_messages`) at
  the end of the stable system block and the end of the stable user block,
  because the Messages API caches only what is explicitly marked. If you write
  an adapter for a provider with its own caching mechanism, use that provider's
  actual primitive; do not assume prefix ordering alone is sufficient.
- The Anthropic adapter uses the native `output_config: {"format": {"type":
  "json_schema", "schema": ...}}` structured-output mechanism (stable, no
  `anthropic-beta` header) and reads the result from the response's single
  `text` content block. The output schema is carried there once, not repeated
  as prompt text, mirroring the Codex `--output-schema` rule above. Anthropic's
  structured-output schema compiler only accepts a limited JSON Schema subset
  (no `minLength`/`maxLength`/`minimum`/`maximum`/`multipleOf`/`maxItems`;
  `minItems` only 0 or 1; every object needs `additionalProperties: false`) and
  returns a 400 for anything else. This project's role schemas use those
  bounds throughout (`agent_runtime/contracts.py`), so the adapter strips them
  before sending (`_strict_output_schema` in `agent_runtime/anthropic_adapter.py`,
  folding each stripped bound into the field's description as a hint instead),
  the same transformation the official SDKs perform client-side for callers who
  use a schema outside that subset. The original, unstripped schema stays the
  sole validation authority: the controller re-checks every returned result
  against it regardless of what the provider enforced during generation, so
  this only loosens generation-time constraints, never final acceptance.

## Self-certifying an adapter

`agent-verify-adapter` (or the source wrapper `scripts/verify_adapter.py`)
uses the same transport and role validators as the controller. By default it
checks only configuration, credentials and the explicit local readiness handshake:

```bash
agent-verify-adapter --policy /absolute/policy.json
```

To authorize a paid synthetic probe, opt in explicitly:

```bash
agent-verify-adapter --policy /absolute/policy.json --live --phase discovery
# All roles, each at most once in this invocation:
agent-verify-adapter --policy /absolute/policy.json --live --phase all
```

`--live` defaults to discovery. Each selected phase gets a fresh 64-hex effect ID;
duplicate selections are collapsed. A failed phase produces a structured failed
report and stops subsequent probes. No automatic retry occurs. Re-running the
command is a **new probe**, potentially spending quota again; this diagnostic is
not the controller's durable receipt ledger. A lost response can have an unknown
outcome, so inspect provider evidence before invoking it again.

A readiness pass is not a live role-contract pass. Neither proves reasoning
quality or production readiness; see [verification limits](VERIFICATION.md).
