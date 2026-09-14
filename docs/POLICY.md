# Policy model

`config/policy.template.json` is intentionally explicit. Policy is the authority envelope between owner intent, product semantics and runtime behavior and should be reviewed as code.

## Repository identity

`product_repo`, `control_repo`, `controller_id`, `owners`, `command_issue` and `base_branch` identify where product changes happen, where execution state lives and who can issue owner commands. Product and control repositories must be different.

## Goal intake

`github_goals` limits what a submitted goal may authorize: enabled state, maximum work items, allowed item ID patterns, maximum risk and maximum auto-merge ceiling. A goal may choose less authority than policy, never more.

The portable example uses `EXAMPLE-*`. Real products should replace it with authored roadmap ID families.

## Read authority

`context_paths` defines files that may enter model context. `phase_context_paths` narrows that set per role and `phase_context_bytes` caps input volume. A path being readable does not make it writable.

## Write authority

`allowed_paths` defines the maximum product write envelope. The example allows implementation source, tests, docs and README while keeping `.agent-control/**`, `.github/**` and `ci/**` owner-controlled.

`critical_paths` are legal changes that force stronger governance. `independent_test_paths` defines where tester-generated executable tests may be added.

## CI identity

Required checks bind both name and trusted application identity. The example uses:

```json
{"name": "agent-control-reference-ci", "app_id": 15368}
```

A same-named status from another integration does not satisfy the gate. `postmerge_checks` are evaluated again on the exact merge SHA.

## Execution budgets

Policy caps changed files, patch size, context size/rounds, protocol repairs, implementation repairs, model calls, CI candidate attempts, timeouts, polling and quota backoff. Exhausting a budget creates a visible blocked state, not permission to skip the gate.

## Deterministic tests

`test_commands` are argv arrays, never free-form shell strings. The example command is:

```json
["python3", "ci/run_tests.py"]
```

The runtime executes deterministic tests in an isolated environment according to the pinned test image and resource limits. `minimum_junit_tests` protects against green zero-test executions.

## Runtime/model binding

Provider-specific fields such as model CLI home/version, model mapping and billing belong to the concrete runtime adapter. They are not portable conceptual requirements except for the general rule that runtime/model identity and fallback behavior must be explicit enough for reproducible evidence.

## Goal contract

`goal_contract` states global priorities, success conditions, forbidden shortcuts and human-decision conditions. It is separate from a single work item because these invariants apply to all work accepted under the policy.

## Adaptive graph and challenge review

`adaptive_agent_graph` selects the smallest safe role graph. `challenge_review` adds an independent review when risk, critical paths, changed-file count or diff size cross configured thresholds. `blocking_medium_kinds` makes selected medium findings blocking rather than advisory.

## What adopters must change

At minimum replace repository names, owners and command issue, roadmap patterns, authority/context/write paths, critical paths, trusted CI identities, test commands and pinned image, resource/time budgets and runtime/model binding.

Do not copy example values into a large production repository and call that policy design. The template exists to make every authority choice visible enough that it has to be considered deliberately.
