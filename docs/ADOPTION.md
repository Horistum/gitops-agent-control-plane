# Adoption guide

This is the supported reference path for a **new tenant** using the exact FlowAI-Control release
pinned in `COMPATIBILITY.json`.

## 0. Preconditions

Use a dedicated unprivileged Linux account. The current engine expects:

- Python 3;
- Git;
- GitHub CLI (`gh`) authenticated to the owner account;
- rootless Podman;
- Codex CLI at an explicitly pinned version;
- ChatGPT authentication in a dedicated `CODEX_HOME`;
- user systemd;
- at least 5 GB free workspace capacity;
- outbound access to GitHub/OpenAI during controller operation.

The control repository must be private and have Issues enabled.

## 1. Create the product repository

Copy `examples/minimal-product/` into a separate repository root.

```bash
mkdir reference-product
cp -a examples/minimal-product/. reference-product/
cd reference-product
git init -b main
git add .
git commit -m "Initial FlowAI-Control reference product"
gh repo create YOUR_ORG/reference-product --private --source . --push
```

Confirm the baseline:

```bash
python3 ci/run_tests.py
```

Then ensure GitHub Actions has produced the `flowai-reference-ci` check at least once.

For a real product, replace the example source, roadmap and authority documents rather than keeping
fake `DEMO-*` semantics.

## 2. Prepare the private control repo

Use a private copy/fork of `gitops-agent-control-plane`. Keep this repository separate from the
product.

Create the command issue:

```bash
gh issue create \
  --title "Flow Loop: řízení a kritická rozhodnutí" \
  --body '<!-- flow-loop:command-issue:v1 -->

Controller is not activated yet. Owner /loop commands belong in new one-line comments.'
```

Record the returned issue number.

Do not use this issue for ordinary discussion. Owner commands must be new, unedited, single-line
comments.

## 3. Prepare the immutable test image

FlowAI-Control runs local verification with `podman --pull=never`, `--network=none`, read-only root,
dropped capabilities and no-new-privileges.

The image therefore must:

- already exist locally;
- be referenced by SHA-256 digest;
- contain the runtime required by every configured `test_commands` entry.

For the minimal Python product, use a Python image you have explicitly pulled and pinned. Obtain the
digest from your environment and verify the exact reference with:

```bash
podman image inspect 'IMAGE@sha256:DIGEST'
```

Do not copy a digest from this documentation. A fake digest is worse than a visible placeholder.

## 4. Prepare Codex authentication

Use a dedicated home:

```bash
export CODEX_HOME="$HOME/.codex-loop"
codex login --device-auth
CODEX_HOME="$CODEX_HOME" codex login status
CODEX_HOME="$CODEX_HOME" codex --version
```

The exact version output becomes policy authority. Changing the installed Codex version later makes
`doctor` fail until you deliberately review/update/reactivate policy.

## 5. Render tenant policy

From the control repo:

```bash
python3 scripts/render_policy.py \
  --product-repo YOUR_ORG/reference-product \
  --control-repo YOUR_ORG/gitops-agent-control-plane \
  --owner YOUR_GITHUB_LOGIN \
  --command-issue ISSUE_NUMBER \
  --controller-id YOUR-UNIQUE-CONTROLLER-ID \
  --test-image 'IMAGE@sha256:64_HEX_DIGEST' \
  --codex-version "$(CODEX_HOME="$HOME/.codex-loop" codex --version)"
```

`policy.json` is mode 0600 and `.gitignore` excludes it. Review it anyway. Authority files deserve
more scrutiny than the average generated YAML avalanche.

For a non-demo product, change at least:

- `github_goals.allowed_item_patterns`;
- context paths;
- allowed/critical paths;
- independent test paths;
- required/post-merge checks;
- test commands and resources;
- goal contract;
- per-phase context budgets.

See `POLICY.md`.

## 6. Establish product `main` governance

First print the exact compatible ruleset payload:

```bash
python3 scripts/product_governance.py --policy policy.json
```

Review it. Then, with product admin rights:

```bash
python3 scripts/product_governance.py --policy policy.json --apply
```

The script refuses to replace an existing `Flow Loop main protection` ruleset. Existing governance
must be inspected/reconciled deliberately, never overwritten because setup wanted a quieter life.

The engine expects an active rule protecting `main`, no bypass actors, no force push/deletion,
pull-request merges with resolved threads, and strict required checks tied to the configured GitHub
App id.

## 7. Install the pinned controller runtime

```bash
python3 scripts/install_runtime.py --policy policy.json
```

By default this performs all of the expensive-but-useful proof steps:

1. clones the runtime source named in `COMPATIBILITY.json`;
2. checks out the exact full SHA;
3. verifies the release manifest against the exact Git tree;
4. installs a versioned immutable runtime copy;
5. runs the controller unit suite;
6. runs `flow_loop doctor`;
7. runs a real data-only Codex smoke turn;
8. runs the product baseline in the pinned rootless Podman image;
9. installs/enables the user `flow-loop.service`;
10. prints the exact policy fingerprint and activation command.

Skip flags exist for controlled diagnostics, not as a recommended production installation.

## 8. Activate explicitly

The service starts paused. In the command issue, post exactly the command printed by the installer:

```text
/loop activate <fingerprint>
```

Use a **new single-line owner comment**. Do not edit it after posting.

The controller will persist the accepted command into `loop-state` and update the control center.

## 9. Run the first GoalEnvelope

Create a new issue using the included **Flow Loop goal** form.

For the minimal product use:

- roadmap item: `DEMO-001`;
- risk ceiling: `LOW` or higher;
- auto-merge: `Jen LOW` if you want a low-risk candidate to merge without another owner approval;
- completion: `DEMO-001 is merged and its post-merge check is green`;
- forbidden directions: keep CI/control-plane changes forbidden.

Do not edit the Goal Issue after submitting it. FlowAI-Control 0.3.0 intentionally rejects edited
Goal Issues because the original immutable issue body is part of authorization provenance.

## 10. Observe

Useful commands:

```bash
systemctl --user status flow-loop --no-pager
journalctl --user -u flow-loop -f
python3 /path/to/runtime -m flow_loop status --config /path/to/policy.json
```

The durable source of truth is the control repo's `loop-state` branch. The command issue is the
operator-friendly projection.

## 11. Move from demo to real product

Do not merely rename `DEMO-001`. Model the real product authority:

1. define roadmap items with explicit acceptance criteria and dependencies;
2. define architecture invariants and forbidden directions;
3. enumerate context paths rather than exposing the repository indiscriminately;
4. set the smallest safe allowed-path envelope;
5. mark security/contracts/migrations as critical;
6. provide deterministic, offline-capable test commands;
7. ensure those commands emit JUnit under `build/test-results/**`;
8. bind required CI checks by exact name and trusted App id;
9. size model/context/CI budgets for the product;
10. validate one deliberately small item before enabling broader auto-merge.
