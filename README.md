# GitOps Agent Control Plane

Reference tenant control-plane for **Horistum FlowAI-Control**.

This repository exists for teams that want to adopt FlowAI-Control without reverse-engineering the
Horistum pilot repository. It separates the three authorities that are easy to accidentally mix:

1. **Runtime source**: reviewed controller code from `Horistum/FlowAi-control`.
2. **Control/state repository**: your private copy of this repository, containing the command surface,
   Goal Issue form and the remote `loop-state` branch written by the controller.
3. **Product repository**: the codebase the controller is allowed to change.

That separation is intentional. Copying the whole controller into every tenant control repo would
make upgrades and provenance needlessly exciting, which software supply chains rarely need.

## Compatibility

This revision is validated against:

- FlowAI-Control `0.3.0`
- source repository `Horistum/FlowAi-control`
- exact reviewed commit `38f7f5c3328d2f8e1b4d6e66dd9750d53cc259a6`
- reference contract `flowai-control-reference/v1`

See [`COMPATIBILITY.json`](COMPATIBILITY.json). The runtime installer refuses to silently follow a
moving `main`; it installs that exact commit.

## Repository map

| Path | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | authority boundaries, data flow and state model |
| `docs/MODEL.md` | agent roles, phases, model selection, retrieval and evidence |
| `docs/ADOPTION.md` | end-to-end installation and first run |
| `docs/POLICY.md` | every important policy group and what adopters should change |
| `docs/OPERATIONS.md` | normal operation, state, commands and recovery rules |
| `docs/SECURITY.md` | threat model and fail-closed boundaries |
| `docs/LIMITATIONS.md` | exact limitations of FlowAI-Control 0.3.0 |
| `config/policy.template.json` | generic engine-compatible policy template |
| `examples/minimal-product/` | copyable product repository with a real green baseline and roadmap item |
| `scripts/render_policy.py` | creates a tenant `policy.json` without committing it |
| `scripts/product_governance.py` | renders or creates the required product `main` ruleset |
| `scripts/install_runtime.py` | installs the pinned controller runtime and user service |
| `scripts/validate_reference.py` | self-check for this reference repository |

## Fast path

The detailed, safer version is in `docs/ADOPTION.md`. The short version is:

```bash
# 1. Copy examples/minimal-product into a separate product repository and push main.
python3 examples/minimal-product/ci/run_tests.py

# 2. In your private control repo create one command issue.
gh issue create \
  --title "Flow Loop: řízení a kritická rozhodnutí" \
  --body '<!-- flow-loop:command-issue:v1 -->

Controller is not activated yet. Owner /loop commands belong in new one-line comments.'

# 3. Prepare Git transport, a pinned local test image and dedicated ChatGPT Codex login.
gh auth setup-git
export CODEX_HOME="$HOME/.codex-loop"
codex login --device-auth
codex --version
podman image inspect 'YOUR_IMAGE@sha256:YOUR_DIGEST'

# 4. Render policy. Never commit policy.json.
python3 scripts/render_policy.py \
  --product-repo YOUR_ORG/YOUR_PRODUCT \
  --control-repo YOUR_ORG/YOUR_CONTROL_REPO \
  --owner YOUR_GITHUB_LOGIN \
  --command-issue 1 \
  --controller-id YOUR_CONTROLLER_ID \
  --test-image 'YOUR_IMAGE@sha256:YOUR_64_HEX_DIGEST' \
  --codex-version "$(CODEX_HOME="$HOME/.codex-loop" codex --version)"

# 5. Inspect, then create the required product ruleset.
python3 scripts/product_governance.py --policy policy.json
python3 scripts/product_governance.py --policy policy.json --apply

# 6. Install and prove the exact pinned runtime.
python3 scripts/install_runtime.py --policy policy.json
```

The installer intentionally does **not** manufacture the `/loop activate <fingerprint>` owner
authorization. It prints the exact command. Post it as a new one-line comment in the command issue.
Then create a **Flow Loop goal** from the included Issue Form for `DEMO-001`.

## What is actually runnable

`examples/minimal-product` is designed to make the first execution observable rather than magical:

- its baseline already passes;
- `ci/run_tests.py` emits JUnit where FlowAI-Control 0.3.0 actually scans it;
- the GitHub Actions job is named exactly `flowai-reference-ci`, matching the policy;
- `DEMO-001` is authorized but intentionally not implemented;
- agent-editable paths are separated from owner-controlled CI and authority documents;
- the goal form preserves the exact v1 protocol labels expected by 0.3.0.

Run the repository self-check at any time:

```bash
python3 scripts/validate_reference.py
```

## Non-goals

This repository is not a second implementation of FlowAI-Control, does not vendor agent role prompts,
does not invent a second state database, and does not make controller upgrades automatic. Runtime
semantics remain owned by `Horistum/FlowAi-control`; this repository is the adoption/reference layer.
