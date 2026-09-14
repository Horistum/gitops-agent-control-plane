# Adoption and first end-to-end run

This procedure creates a clean demonstration with separate product and control repositories.

## 1. Prerequisites

Use a dedicated unprivileged Linux user with Git, GitHub CLI, Python 3.11+, rootless Podman, systemd user services, the model CLI required by the active runtime adapter, GitHub write access to product/control repositories and sufficient product privileges to establish governance.

The control repository should be private and have Issues enabled.

## 2. Create the example product

Copy `examples/minimal-product` into a new separate repository:

```bash
mkdir ~/agent-reference-product
cp -a examples/minimal-product/. ~/agent-reference-product/
cd ~/agent-reference-product
git init -b main
git add .
git commit -m "Initial autonomous-delivery reference product"
git remote add origin git@github.com:YOUR_ORG/YOUR_PRODUCT.git
git push -u origin main
```

Verify the baseline before involving any model:

```bash
python3 ci/run_tests.py
```

Three tests must pass and `build/test-results/reference/TEST-reference.xml` must contain three testcase identities. Push once and confirm the GitHub Actions job named `agent-control-reference-ci` succeeds.

## 3. Create the control repository

Create a separate private repository with Issues enabled. This repository is not the product and should not contain product source.

Create one long-lived control issue:

```bash
gh issue create --repo YOUR_ORG/YOUR_CONTROL_REPO \
  --title "Agent Control Center" \
  --body "Owner control channel. Generated status is managed by the controller."
```

Record the issue number.

## 4. Prepare deterministic test infrastructure

Build a product-specific container image containing the tools required by `test_commands`. Load it into rootless Podman on the controller host and obtain its immutable digest.

The runtime executes with no network and no floating pull, so the image must exist locally under the exact digest.

## 5. Authenticate the model runtime

Use the dedicated credential home required by the active adapter. Do not reuse a general shell environment containing unrelated API or repository secrets. Verify the exact CLI version after login; that version becomes part of runtime identity.

## 6. Render tenant policy

```bash
python3 scripts/render_policy.py \
  --product-repo YOUR_ORG/YOUR_PRODUCT \
  --control-repo YOUR_ORG/YOUR_CONTROL_REPO \
  --owner YOUR_GITHUB_LOGIN \
  --command-issue YOUR_ISSUE_NUMBER \
  --controller-id YOUR_CONTROLLER_ID \
  --test-image 'YOUR_IMAGE@sha256:YOUR_64_HEX_DIGEST' \
  --codex-version 'YOUR_EXACT_MODEL_CLI_VERSION'
```

Inspect `policy.json`. The renderer refuses obvious identity/digest mistakes, but it cannot decide your real architecture or critical paths for you.

## 7. Establish product governance

Preview:

```bash
python3 scripts/product_governance.py --policy policy.json
```

Apply after inspection:

```bash
python3 scripts/product_governance.py --policy policy.json --apply
```

The helper requires pull requests, resolved review threads, no delete/force-push and exact trusted status checks on `main`. It will not silently replace an existing ruleset with the same name.

## 8. Install and prove the runtime adapter

```bash
python3 scripts/install_runtime.py --policy policy.json
```

The installer validates repositories and control issue, fetches the exact pinned runtime, verifies its release manifest/file set, runs runtime unit tests and doctor, performs a real model protocol smoke and executes the real product baseline in the isolated test container.

A successful install prints a runtime fingerprint.

## 9. Activate through the portable operator interface

```bash
python3 scripts/control.py --policy policy.json \
  activate --fingerprint THE_PRINTED_FINGERPRINT
```

The wrapper posts the exact backend command to the configured control issue. Backend-specific syntax is intentionally not part of the operator contract.

## 10. Submit the first goal

Review `examples/goal.example.json`, then:

```bash
python3 scripts/submit_goal.py --policy policy.json --file examples/goal.example.json
```

The goal authorizes `EXAMPLE-001`, allows medium risk, permits automatic merge only through low risk and forbids CI/authority changes.

## 11. Expected lifecycle

A successful run should produce accepted goal evidence, selected `EXAMPLE-001`, architecture plan and bounded working set, implementation adding `greet()`, executable independent tests, green local verification, a product pull request, green `agent-control-reference-ci` on the exact candidate SHA, merge according to risk authority, green post-merge check on the exact merge SHA and durable completion evidence.

Inspect all of it. A reference system that cannot be understood on its smallest example will not become more understandable after being pointed at a large production repository.

## 12. Adapt to a real repository

Do not simply rename `EXAMPLE-001`. Replace the example authority model with real architecture constraints, roadmap identifiers/dependencies, deterministic build/test commands, critical/public/security paths, trusted CI checks, realistic context/cost budgets and human decision boundaries.

Then rerun the complete installation/live-verification path before granting auto-merge authority.
