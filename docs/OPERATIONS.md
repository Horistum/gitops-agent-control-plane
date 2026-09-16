# Run the operational controller

Use Linux or WSL, Python 3.11+, Git, supported Codex CLI and rootless Podman.
Install the distribution with `python3 -m pip install .`, or use
`./scripts/agentctl run` instead of the installed `agent-control` command.
The controller runs as the owner; no daemon or web interface is required.

## Prepare one bounded product goal

1. Use a clean product Git checkout. Its `origin` must identify the configured
   GitHub repository and its base must equal the current remote branch.
2. Copy `examples/operational/policy.example.json` and `goal.example.json` outside
   that product. Replace all placeholder paths, repository identity, context,
   criteria, test commands, JUnit selectors and required check names/App IDs.
3. Authenticate the trusted Codex CLI using the owner's ChatGPT account. Set
   `reasoning.codex_home` to that authenticated directory; `doctor` checks required
   CLI capabilities. The implementation is checked against Codex 0.153.4. Model
   availability and quota belong to the account; an empty model uses its default.
4. Prepare the product's build image and dependencies before the run. Pin the
   image by a locally available repository digest. Execution never pulls images
   or enables the container network. For a Python-only experiment, for example:

   ```bash
   podman pull docker.io/library/python:3.12-slim
   podman image inspect docker.io/library/python:3.12-slim --format '{{index .RepoDigests 0}}'
   ```

5. Provide the controller's GitHub credential through the configured environment
   variable (the example uses `GH_TOKEN`) and configure Git's transport separately.
   Credentials are not copied into model prompts, model environment, product
   snapshots, containers or receipts. Keep them out of policy JSON and Git.
6. Protect the target branch with PRs, resolved review threads, strict required
   checks bound to the declared App IDs, and no delete/force-push bypass. Classic
   protection or compatible active rulesets are supported. Permit two-parent
   merge commits. The controller reads and enforces protection; it does not alter it.

The policy is operator authority; models never choose executable commands. Keep
verification tools and existing tests protected. Grant only the source paths the
bounded goal needs. The example goal is illustrative and must match the actual
product; it is not inferred from README prose.

Item IDs use letters, digits, hyphens and underscores. Behavior criteria require
new-behavior negative controls; compatibility criteria require regression bindings.
Policy CLI cases are invariants checked on every candidate and merged item, so
they must be valid at every intermediate delivery stage. Item-specific future
behavior belongs in the corresponding item's acceptance criteria.

```bash
agent-control doctor --policy /absolute/policy.json --goal /absolute/goal.json
agent-control start --policy /absolute/policy.json --goal /absolute/goal.json \
  --state /absolute/agent-runs/my-goal
agent-control status --state /absolute/agent-runs/my-goal
agent-control resume --state /absolute/agent-runs/my-goal
```

`doctor` makes prerequisite/governance observations but makes no model call and
cannot certify account quota or a product build. `start` creates a private,
run-owned bare Git repository. Model proposals and tests operate on exact snapshots.
GitHub publication pushes an attempt branch and opens/reconciles its PR. It never
pushes directly to the protected base. Model-generated code does not run on the
controller host in the GitHub profile.

`resume --poll-seconds 30` waits without spending model turns while CI is pending.
Each invocation has a step bound; `--max-steps` controls it. Exit 0 means the goal
completed; exit 2 means inspect status or continue the pending run. `status` is
read-only. The final merge SHA and private receipts define the validation scope.

## Alternative reasoning and local operation

`reasoning.kind=command` invokes the owner-provided `argv` in an empty directory
with an allowlisted environment. Stdin contains `{instructions,input,output_schema}`;
stdout must contain one JSON object matching that phase's schema. The command
provider is trusted infrastructure: it must authenticate to its own model service
without receiving product/GitHub credentials. No fixture implementation is selected
by operational configuration. `agent-control schema developer` prints the contract.

For owner-trusted local code, choose `publication.kind=local` and
`execution.kind=trusted-local`, then pass `--trusted-local` to `start`. This mode
executes real tests and merges into `<state>/product.git`; the original checkout
stays intact. GitHub publication and CI-specific criteria are unavailable in this
mode. Inspect/fetch the resulting commits from the run-owned repository. Local
execution is not a sandbox for untrusted generated code.

## Owner decisions and recovery

| Status or action | Behavior |
|---|---|
| `RUNNING` | Continue the bounded loop |
| `WAITING_EXTERNAL` | No success inferred; resume observes the provider again |
| `NEEDS_DECISION` | Approve the exact displayed binding, or replan/cancel |
| `FAILED` | Inspect concrete failed verification/CI; `retry` is available only for a retryable hold |
| `BLOCKED_POLICY` | No ordinary approval bypass; inspect the policy, identity or protocol reason |
| `pause` / `continue` | Change authoritative pause state; in-progress effects first finish under the writer lock |
| `replan` | Close/reconcile an unmerged PR, retire the attempt, preserve frozen tests and allocate new identities |
| `cancel` | Retire only after pending/merge races are resolved; does not undo a merge |
| `reconcile` | Re-observe/replay a pending non-model effect before other work |
| `retry-effect --binding ID` | Explicitly accept another call after an unrecorded model outcome; lifetime budget remains consumed |

```bash
agent-control approve --state /absolute/agent-runs/my-goal --binding DISPLAYED_HASH
agent-control retry --state /absolute/agent-runs/my-goal
agent-control replan --state /absolute/agent-runs/my-goal
```

An approval is invalid after the candidate, base, risk, goal, policy or runtime
changes. Replanning does not reset the run's model-call budget. A post-merge failure
blocks subsequent work; this runtime does not automatically roll back a product.

Pause the old runtime before changing its installed source. At a quiescent boundary:

```bash
agent-control pause --state /absolute/agent-runs/my-goal
# install the reviewed new controller version
agent-control upgrade --state /absolute/agent-runs/my-goal
agent-control continue --state /absolute/agent-runs/my-goal
agent-control resume --state /absolute/agent-runs/my-goal
```

`upgrade --suspend` is limited to a held unchanged attempt with no PR, merge,
checkpoint or pending effect. It cannot migrate an in-flight candidate by relabeling it.

## Reproducible fixture demonstrations and development checks

```bash
./scripts/agentctl demo happy-path
./scripts/agentctl loop
./scripts/agentctl demo repair-loop
./scripts/agentctl validate
python3 -m pip install -r requirements-test.txt
PYTHONPATH=. python3 tests/test_schema_interoperability.py --require-reference -v
```

These `demo`/`loop` commands use trusted deterministic fixtures. Their local
property-probe executor is not the operational container profile. Results live
under `.demo/runs/`; `agentctl cleanup` removes only demo artifacts. The legacy
bootstrap/diagnose commands check the fixture's Python/Git prerequisites.

Actual rootless execution can be reproduced independently with
`python3 scripts/check_podman_runtime.py --image PINNED_IMAGE`. It executes a real
container lifecycle with a test protocol peer; it does not authenticate a model.

Official transport references: [Codex non-interactive output](https://learn.chatgpt.com/docs/non-interactive-mode),
[Codex CLI options](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
[Podman execution](https://docs.podman.io/en/latest/markdown/podman-run.1.html),
[GitHub merge API](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request).
