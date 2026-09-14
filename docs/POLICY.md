# Policy guide

`config/policy.template.json` is intentionally complete rather than cute. FlowAI-Control treats the
policy as authority and fingerprints it together with trusted runtime/role bytes.

## Repository identity

- `product_repo`: repository the controller may change.
- `control_repo`: private state/command repository.
- `controller_id`: stable single-writer identity for this controller instance.
- `owners`: GitHub user logins authorized to create goals and owner commands.
- `command_issue`: dedicated control-center issue number.
- `base_branch`: 0.3.0 requires `main`.

Product and control repositories must differ.

## Goal intake

`github_goals` bounds GitHub Issue authorization:

- `enabled`;
- `max_items` from 1 to 50;
- `allowed_item_patterns`;
- `max_risk`;
- `max_auto_merge_risk`.

The static policy is the outer authority ceiling. A Goal Issue may choose a narrower ceiling, never a
broader one.

`approved_items` remains empty for the GitHub-native v0.3.0 path.

## Read context

`context_paths` is the global allowlist of authority/data files that phases may receive.

`phase_context_paths` must define exactly these ten keys:

```text
discovery
architect
test_design
chief_plan
developer
tester
reviewer
challenge_review
architect_accept
chief_accept
```

Every phase path must also be present in `context_paths`.

`phase_context_bytes` applies a separate byte budget to each phase and may never exceed
`max_context_bytes`.

## Write envelope

`allowed_paths` is what normal product work may modify.

`critical_paths` are allowed but force stronger treatment. Use them for public contracts, security,
migrations, semantic kernels and similar high-consequence areas.

`independent_test_paths` identifies paths the independent tester may use to add executable tests.

The engine additionally hard-denies control/security surfaces such as Git metadata, GitHub
workflows/actions, Codex instructions and core `.flow-agent` authority files. Do not add them to
`allowed_paths` expecting policy to override the engine.

In this reference, `ci/` and `.github/workflows/` are deliberately not agent-editable.

## Required GitHub checks

Every required check is bound by **both** name and trusted GitHub App id:

```json
{"name": "flowai-reference-ci", "app_id": 15368}
```

Do not guess check names. Observe the actual GitHub check run produced by the product workflow.

`postmerge_checks` apply the same principle to the exact merge SHA.

## Local tests

`test_commands` are argv arrays, never shell command strings.

The reference uses:

```json
[["python3", "ci/run_tests.py"]]
```

The controller exports product source into a temporary workspace and executes every command in the
pinned Podman image with network disabled.

FlowAI-Control 0.3.0 scans JUnit under:

```text
**/build/test-results/**/*.xml
```

A zero exit code alone is not enough. `minimum_junit_tests` requires observed executed test
identities. The example runner demonstrates the smallest portable way to satisfy this for Python.

`test_image` must be SHA-256 pinned and already local because the test runner uses `--pull=never`.

## Model execution

- `codex_home`: dedicated ChatGPT-authenticated Codex home.
- `codex_version`: exact `codex --version` output.
- `models`: role-to-model map or `{}` for Codex default.
- `agent_timeout_seconds`: per model turn.
- `max_agent_calls_per_day` / `max_agent_calls_per_task`: hard call budgets.
- `soft_token_budget_per_task`: planning/convergence budget, not authority expansion.

The supported billing contract is fixed to ChatGPT usage with no API fallback.

## Patch and convergence bounds

- `max_changed_files`
- `max_patch_bytes`
- `max_context_rounds`
- `max_protocol_repairs`
- `max_repairs`
- `max_ci_candidates_per_day`
- `max_ci_candidates_per_task`

Use tight defaults. Increasing limits because a task does not converge can hide a bad task boundary.

## Challenge review

`challenge_review` can trigger on:

- medium/high risk;
- critical-path edits;
- changed-file threshold;
- diff-byte threshold.

The reference treats correctness, architecture, compatibility, security, testing, scope and evidence
as blocking medium-severity finding classes.

## Goal contract

`goal_contract` is the stable operating constitution above an individual Goal Issue:

- objective;
- priority order;
- success conditions;
- forbidden shortcuts;
- human-decision conditions.

Keep these generic and durable. Put item-specific acceptance criteria in the product roadmap and
bounded objective in the Goal Issue.

## Auto-merge

Three distinct controls interact:

1. top-level `auto_merge`;
2. static `github_goals.max_auto_merge_risk`;
3. per-GoalEnvelope selected auto-merge ceiling.

Critical paths and high-risk work still force owner decision boundaries where the engine requires
them. “Auto merge” is not “skip evidence.”
