# Adoption and first end-to-end run

This procedure creates a clean reference deployment with separate product and control repositories, explicit GitHub governance, a pinned runtime adapter and one intentionally small live goal.

For Linux host provisioning, service lifecycle and diagnostics, see `LINUX.md`.

## 1. Validate the reference before touching external systems

From the reference repository:

```bash
./scripts/agentctl validate
```

This offline suite executes the minimal-product baseline, inspects JUnit identities, validates policy/goal/control/governance contracts, compiles Python and checks Linux Bash scripts. It does not authenticate a model and does not mutate GitHub.

On Linux, also run:

```bash
./scripts/agentctl bootstrap check
```

If prerequisites are missing on a supported Debian/Ubuntu or Fedora/RHEL-family host:

```bash
./scripts/agentctl bootstrap prepare
```

The controller/runtime itself must run under a dedicated unprivileged user.

## 2. Create the example product repository

Copy `examples/minimal-product` into a new repository:

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

The example's `.agent-control/` directory is product-authored authority. It is intentionally outside the controller write envelope.

## 3. Create the separate control repository

Create a **different private repository** with Issues enabled. It stores the owner/control surface and the remote execution-state branch; it must not contain product source.

Create one long-lived control issue:

```bash
gh issue create --repo YOUR_ORG/YOUR_CONTROL_REPO \
  --title "Agent Control Center" \
  --body "Owner control channel. Generated status is managed by the controller."
```

Record the issue number.

## 4. Prepare deterministic test infrastructure

Build or choose a product-specific container image containing exactly the tooling required by `test_commands`.

Load it into rootless Podman on the controller host and obtain its immutable digest:

```bash
podman image inspect YOUR_IMAGE --format '{{.Digest}}'
```

The runtime executes product verification with no network and no floating pull, so the image must exist locally under the exact digest used by policy.

Never put credentials into the test image.

## 5. Authenticate GitHub and the runtime/model CLI

GitHub:

```bash
gh auth login --hostname github.com
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
```

The portable architecture does not require one particular model provider. The active runtime adapter may require its own CLI and authentication home. Authenticate that CLI separately and record the **exact** version in policy.

Do not put a broad API key into `policy.json`.

## 6. Render tenant policy

Using the Linux/Bash front end:

```bash
./scripts/agentctl render-policy \
  --product-repo YOUR_ORG/YOUR_PRODUCT \
  --control-repo YOUR_ORG/YOUR_CONTROL_REPO \
  --owner YOUR_GITHUB_LOGIN \
  --command-issue YOUR_ISSUE_NUMBER \
  --controller-id YOUR_CONTROLLER_ID \
  --test-image 'YOUR_IMAGE@sha256:YOUR_64_HEX_DIGEST' \
  --codex-version 'YOUR_EXACT_RUNTIME_MODEL_CLI_VERSION'
```

The direct Python command remains available:

```bash
python3 scripts/render_policy.py ...
```

Inspect `policy.json`. The renderer refuses obvious identity/digest mistakes, but it cannot decide your real architecture, authority paths or risk model for you.

`policy.json` is intentionally ignored by Git. Treat it as host-local reviewed configuration.

## 7. Establish product governance

Preview the exact desired ruleset:

```bash
./scripts/agentctl governance --policy policy.json
```

Apply only after inspection:

```bash
./scripts/agentctl governance --policy policy.json --apply
```

The helper requires pull requests, resolved review threads, no delete/force-push and exact trusted status checks on `main`. It will not silently replace an existing incompatible ruleset with the same name.

## 8. Install and prove the pinned runtime adapter

```bash
./scripts/agentctl install --policy policy.json
```

The installer validates repositories and the control issue, fetches the exact pinned runtime source, verifies its release manifest and exact file set, runs adapter unit tests and doctor, performs a real model protocol smoke, executes the real product baseline in the isolated test container and installs the user systemd service.

A successful install prints exact runtime source commit, immutable installed runtime directory, policy/work directories, service identity, runtime/policy fingerprint and the portable activation input.

The service is not considered owner-authorized merely because installation succeeded.

## 9. Activate through the portable operator interface

Use the fingerprint printed by installation:

```bash
./scripts/agentctl control --policy policy.json \
  activate --fingerprint THE_PRINTED_FINGERPRINT
```

The wrapper translates this portable action into the currently pinned runtime protocol. Backend-specific syntax is deliberately not the operator contract.

## 10. Submit the first portable goal

Inspect:

```bash
cat examples/goal.example.json
```

Then submit:

```bash
./scripts/agentctl goal --policy policy.json \
  --file examples/goal.example.json
```

The goal authorizes `EXAMPLE-001`, allows medium risk, permits automatic merge only through low risk and forbids CI/authority changes.

## 11. Observe the expected lifecycle

A successful live run should create evidence for all of the following:

1. goal accepted with immutable source identity/hash;
2. `EXAMPLE-001` selected from product-authored roadmap authority;
3. bounded architecture plan and working set;
4. implementation adding `greet()` while preserving normalization behavior;
5. deterministic local verification;
6. executable independent tests and independent review evidence;
7. product pull request bound to the exact candidate SHA;
8. green trusted `agent-control-reference-ci` for that exact candidate;
9. merge only when risk/governance/authority permit it;
10. green post-merge check on the exact merge SHA;
11. durable completion state/evidence.

Inspect each artifact. A reference system that cannot be understood on its smallest example will not become more understandable after being pointed at a large production repository.

## 12. Normal owner controls

Portable commands include:

```bash
./scripts/agentctl control --policy policy.json pause
./scripts/agentctl control --policy policy.json drain
./scripts/agentctl control --policy policy.json resume
./scripts/agentctl control --policy policy.json refresh
```

Retry, approval, replanning and goal cancellation additionally require the exact task/goal ID and hash rendered by the control plane. That prevents a stale human decision from silently approving a changed candidate.

## 13. Diagnostics

Read-only host/reference diagnostics:

```bash
./scripts/agentctl diagnose --policy policy.json
```

See `LINUX.md` for detailed systemd, rootless Podman, log and uninstall procedures.

## 14. Adapt the reference to a real repository

Do not merely rename `EXAMPLE-001`.

Replace the example authority model with real architecture constraints and invariants, roadmap IDs and dependency rules, deterministic build/test commands, critical/public/security paths, trusted CI check identities, context/cost/time budgets, risk thresholds and explicit human-decision conditions.

Then rerun both the offline reference validation and complete live installation/verification path before granting auto-merge authority.

## 15. What success actually proves

Passing `scripts/validate_reference.py` proves the **reference repository layer**.

A successful runtime installation additionally proves the **host/runtime integration layer**.

Only a completed live goal with exact candidate/post-merge evidence proves the **end-to-end delivery lifecycle**.

These are deliberately separate claims. Combining them into one vague "it works" badge would be shorter, but considerably less useful.
