# Experimental brokered worker

The optional `codex-app-server-broker/v1` profile uses the official Codex app-server stdio interface. It is disabled unless the owner adds the worker configuration and reviews the resulting policy/runtime fingerprint. Existing reasoning transports remain available. Capability failure never selects a compatibility transport automatically.

The portable `agent_worker` package has no repository-adapter imports. It registers only `read_source`, `search_source`, and, in authorized development/test phases, `stage_edits`. Source comes from exact Git objects through the controller. Edits remain an in-memory overlay until normal controller validation and application. Every staged overlay receives the adapter's path, working-set, source-hash, protected-file, frozen-test and size checks. Ordinary argument mistakes return bounded tool errors for correction within the same turn. Authority violations, unexpected tools and protocol errors stop the turn.

The worker has no command, test execution, web, MCP, app, goal, subagent, plugin, hook, browser or computer capability. The reviewed CLI runs with an empty temporary working directory and HOME, a dedicated owner-managed CODEX_HOME, an allowlisted environment, strict effective configuration, and a named read-only/network-disabled permission profile. The authenticated process necessarily has its own authentication and session storage. This design trusts the pinned CLI, host account and operating system; it does not make arbitrary authenticated shell access safe. No shell is offered. Product text is untrusted data, not authority.

## Pin and anonymous capability check

Codex 0.153.4 does not expose the exec-only `--ignore-user-config` and `--ignore-rules` options on app-server. The worker uses actual advertised `app-server --strict-config --stdio` flags, rejects configuration/instruction/plugin ingress in its dedicated home, and checks every capability override through `config/read` before dispatch. Managed permission requirements must allow the named profile.

The following command generates the experimental official schema, checks its digest, initializes an anonymous app-server, and verifies effective configuration and permissions. It does not read authentication or create threads/turns:

```sh
python -m agent_worker.capabilities --codex codex \
  --expected-version 'codex-cli 0.153.4' \
  --expected-schema-sha256 2af3f81b7de53f1b1bc7ce6e7349288b200ecf6f6c59405d632cf6ca1d5be1d0
```

The reviewed schema bundle contains 416 files. Dynamic tools are experimental; a different CLI/schema needs explicit review. The anonymous capability command was exercised against the actual pinned binary. Controlled subprocess fixtures test dispatch, retrieval, revisions, histories, errors and crash boundaries. Neither is evidence that a live provider turn passed on a deployment host.

## Configuration and commissioning

Set the adapter's optional worker object to this shape, using an owner-controlled absolute attestation path:

```json
{
  "profile": "codex-app-server-broker/v1",
  "experimental": true,
  "codex_version": "codex-cli 0.153.4",
  "schema_sha256": "2af3f81b7de53f1b1bc7ce6e7349288b200ecf6f6c59405d632cf6ca1d5be1d0",
  "max_tool_calls": 24,
  "max_tool_bytes": 1000000,
  "max_frame_bytes": 1000000,
  "max_output_bytes": 8000000,
  "timeout_seconds": 600,
  "smoke_attestation": "/absolute/private/worker-smoke.json"
}
```

The operational reference adapter accepts this at `reasoning.worker` with `reasoning.kind="codex"`, its normal executable argv/model, and a dedicated absolute `codex_home`. Its activation preflight requires a matching successful smoke attestation. Before activation, run the explicitly authorized target-host commissioning command:

```sh
python -m agent_worker.smoke --policy /absolute/policy.json --adapter-module agent_runtime.worker
```

This selects the configured model and reserves one potentially billed app-server turn. It must search/read synthetic source and stage the exact expected replacement through all three tools. It writes no product changes and runs no product tests. The attestation binds the worker source, full profile, exact requested model, CLI/schema pin and the adapter authority source hash (source broker, path/content validation and their authorization dependencies). The live turn exercises the synthetic broker only. It does not execute the production adapter authorizer; separate adapter regression tests exercise that boundary. Binding reviewed code does not certify product behavior. Each configured model requires its own explicitly requested smoke (`--model MODEL`); attestations for different models coexist. Production preflight and every dispatch require the matching model and adapter identity. Changing authority code invalidates prior smoke evidence; legacy commissioning intents require review and explicit `--retry-smoke`, never an automatic repeat.

Commissioning keeps a durable intent, turn journal, lock and receipts beside the attestation. Repeating the command reuses matching completed evidence. An uncertain dispatched turn cannot repeat automatically. After reviewing the outcome, `--retry-smoke` explicitly authorizes another reserved turn and preserves prior evidence. Failed retried commissioning removes the previous attestation for that model before dispatch; attestations for other models remain separate. Protect these records like controller state; never copy fixture attestations into a deployment.

## Histories, recovery and budgets

Each task/attempt/phase/head/specification/authority/model/profile identity owns a separate session. Only completed histories resume. Review and test-design phases cannot inherit a developer session. A dispatched turn writes durable intent before `turn/start`; ambiguous outcomes hold rather than automatically repeat. Both adapters can adopt an exact completed inner receipt before requiring owner reconciliation, without CLI, authentication or provider I/O. Changed request or authority cannot reuse it. Explicit retry of an unknown effect uses a new operation and fresh thread.

Controller model-call and daily-call limits count reserved app-server turns. One turn may contain multiple internal model inferences behind broker calls; these limits do not promise an exact provider-request count or bill. Tool operations, argument/response bytes, protocol frames, aggregate output and elapsed time are separately bounded. Failed correctable tool calls consume the same bounds. Observed cumulative token usage is converted to per-turn deltas before accounting. Existing soft token budgets, independent tests, review, acceptance, CI and publication gates remain authoritative.

Private worker records and provider histories contain source-derived data and are local operational state, never publication artifacts. Maintain the controller's existing single-owner process discipline and preserve journals during recovery or upgrades. A profile smoke is separate from the independently required product baseline and execution evidence.

Official interface documentation: [app-server](https://learn.chatgpt.com/docs/app-server), [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). The generated schema and strict configuration checks of the exact pinned binary are the compatibility gate when current documentation describes newer features.

## Defensive I/O and proposal validation

Direct final JSON and `stage_edits` share path, original/overlay hash, text, NUL, deletion, uniqueness, no-op and aggregate patch bounds before adapter authorization. Session and commissioning locks reject symlinks (including parent directories), nonregular files and multiply linked files before acquiring a nonblocking OS lock. Capability inspection bounds stdout plus stderr while the process runs and terminates its process group on excess output or deadline. Controlled pipe tests cover split frames, oversized and aggregate output, read/write deadlines, backpressure and child cleanup; they are not live provider evidence.
