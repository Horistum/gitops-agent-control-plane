# Linux host guide

This guide covers the reference control-plane host on a conventional Linux workstation, VM or small server. It complements `ADOPTION.md`: this file is about the host itself; `ADOPTION.md` is about product/control repositories and the first live goal.

## Supported host profile

The portable reference requires:

- Linux with a normal unprivileged user;
- Python 3.11 or newer;
- Git and GitHub CLI;
- rootless Podman;
- a working `systemd --user` manager;
- enough local disk for repository clones, container layers and evidence;
- outbound HTTPS to GitHub and the model/runtime provider;
- no inbound network listener for the reference controller.

`scripts/bootstrap-linux.sh` currently provisions Debian/Ubuntu and Fedora/RHEL-family package sets. Other distributions may work, but are intentionally not guessed by the provisioning path.

The default free-space floor is 8 GiB and can be raised:

```bash
export AGENT_CONTROL_MIN_FREE_GB=20
```

## 1. Offline repository validation

This does not install anything and does not contact a model:

```bash
./scripts/agentctl validate
```

It executes the example product baseline, checks JUnit identities, policy consistency, goal/control adapters, governance payloads, portable/backend boundaries, Python compilation and shell syntax/self-tests.

## 2. Read-only host check

```bash
./scripts/agentctl bootstrap check
```

The check verifies the Linux distribution family, commands, free disk, user systemd manager and rootless Podman. GitHub/model authentication is reported but not modified.

## 3. Provision OS prerequisites

```bash
./scripts/agentctl bootstrap prepare
```

For automation where package installation has already been reviewed:

```bash
./scripts/agentctl bootstrap prepare --yes
```

The provisioning path may use `sudo` only for OS packages, subordinate UID/GID ranges and `loginctl enable-linger`. The controller itself must never run as root.

If subordinate ID ranges were newly created, log out and back in once before retrying `bootstrap check`. Rootless container namespaces are attached to the login session; pretending a changed `/etc/subuid` retroactively changed the current session would be convenient, but Linux remains stubbornly literal.

## 4. GitHub authentication

Authenticate the dedicated host identity:

```bash
gh auth login --hostname github.com
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
```

The identity needs the repository permissions described in `SECURITY.md` and `ADOPTION.md`. Do not export a broad token in shell profiles if the GitHub CLI credential store can be used.

## 5. Runtime/model CLI

The portable architecture does not prescribe a model vendor. The active `runtime_adapter` in `COMPATIBILITY.json` may require an additional CLI and authentication flow.

Install that adapter dependency through its reviewed distribution channel, authenticate it in a dedicated credential home and record the exact version in the rendered policy.

Do not put a general API key into `policy.json`.

## 6. Prepare product and control repositories

Follow `ADOPTION.md` to create:

1. a product repository containing the copied `examples/minimal-product`;
2. a separate private control repository with Issues enabled;
3. one long-lived control issue.

The two repository identities must differ.

## 7. Render policy

The Bash front-end delegates to the reviewed Python renderer:

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

Review `policy.json`; do not commit it.

## 8. Establish product governance

Preview first:

```bash
./scripts/agentctl governance --policy policy.json
```

Apply only after inspection:

```bash
./scripts/agentctl governance --policy policy.json --apply
```

The helper is deliberately fail-closed around an existing incompatible ruleset.

## 9. Install and prove the runtime adapter

```bash
./scripts/agentctl install --policy policy.json
```

The installer performs repository/control-issue preflight, exact pinned Git checkout verification, release-manifest and exact-file-set verification, adapter unit tests, doctor/preflight, model protocol smoke, real isolated product baseline and systemd user-service installation.

A successful install prints the exact runtime fingerprint needed for owner activation.

## 10. Activate and submit the first goal

```bash
./scripts/agentctl control --policy policy.json \
  activate --fingerprint THE_PRINTED_FINGERPRINT

./scripts/agentctl goal --policy policy.json \
  --file examples/goal.example.json
```

These interfaces are portable. Backend-specific comment syntax remains inside the adapter scripts.

## 11. Service lifecycle

The installed user service is:

```text
agent-control-plane.service
```

Useful commands:

```bash
systemctl --user status agent-control-plane.service
systemctl --user restart agent-control-plane.service
systemctl --user stop agent-control-plane.service
journalctl --user -u agent-control-plane.service -f
```

Use the control-plane `pause`/`drain` commands for normal operational boundaries. Stopping systemd is a host-level intervention, not a substitute for durable control state.

## 12. Diagnostics

Run the read-only diagnostic bundle:

```bash
./scripts/agentctl diagnose --policy policy.json
```

It reports host/toolchain information, GitHub authentication state, rootless Podman security, reference integrity, policy JSON, systemd status, recent logs and local evidence files. It does not mutate GitHub or controller state.

## 13. Safe local uninstall

Default uninstall stops/disables the local service and removes only its user unit:

```bash
./scripts/agentctl uninstall
```

To additionally remove immutable local runtime copies:

```bash
./scripts/agentctl uninstall --purge-runtime
```

To remove the local working/evidence directory as well:

```bash
./scripts/agentctl uninstall --purge-runtime --purge-state
```

The uninstall script **never deletes remote GitHub repositories, pull requests, issues or the authoritative state branch**. Remote state should be retained until the owner has explicitly decided its retention/migration path.

## 14. Moving to another Linux host

Do not run two active writers with the same controller identity.

A safe migration boundary is:

1. stop accepting new work;
2. drain/pause at a verified task boundary;
3. confirm no pending external effect;
4. stop the old service;
5. preserve the remote authoritative state;
6. prepare the new host;
7. use the runtime adapter's explicit controller-transfer mechanism when required;
8. reactivate using the new exact runtime/policy fingerprint.

The portable rule is single-writer ownership. The concrete transfer transaction is adapter-specific and belongs behind the runtime adapter boundary.

## Troubleshooting checklist

If installation fails, work top-down rather than randomly reinstalling things:

```bash
./scripts/agentctl validate
./scripts/agentctl bootstrap check
./scripts/agentctl diagnose --policy policy.json
```

Then inspect:

- `gh auth status --hostname github.com`;
- `podman info`;
- exact local test image digest;
- exact model/runtime CLI version;
- user systemd availability and linger;
- product/control repository permissions;
- required GitHub check identity;
- recent service logs.

A failed hard gate should stay failed until its cause is understood. Replacing a precise error with a larger pile of automation is an old human tradition, but not a useful recovery strategy.
