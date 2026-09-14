# Security model

## 1. Models are not the privileged executor

The controller, not the LLM, holds GitHub authority and runs tests. Model sessions are constrained to
read-only structured proposal work without shell, web, subagents or inherited GitHub credentials.

This reduces prompt-injection impact: malicious repository text can influence a proposal, but it
cannot directly execute a shell command or push a branch from the model session.

## 2. Product changes are path-bounded twice

A candidate must satisfy:

1. tenant `allowed_paths`;
2. engine hard-deny paths.

The second layer prevents a product goal from authorizing edits to controller-sensitive surfaces such
as workflows, Git metadata and trusted agent/authority instructions.

## 3. Tests are isolated

Local verification is executed by the controller in rootless Podman with:

- no network;
- read-only root filesystem;
- all Linux capabilities dropped;
- no-new-privileges;
- pid, memory and CPU bounds;
- temporary HOME and Gradle home;
- exact preloaded image;
- fixed owner-approved argv commands.

The product source is the writable mounted workspace. Credentials are not intentionally passed into
the container.

## 4. CI identity matters

A green string named `flowai-reference-ci` is insufficient by itself. Policy binds required checks
to the GitHub Actions App id.

Product governance also requires strict checks against current `main` and blocks force push/deletion.

## 5. State integrity

`loop-state` uses:

- single `controller_id` writer identity;
- non-force pushes;
- sequence numbers;
- previous-event hashes;
- state hashes;
- immutable run receipts.

A disappeared established state branch, wrong controller identity or inconsistent event hash fails
closed.

## 6. Exact-SHA evidence

Baseline, candidate, CI, merge and post-merge evidence are tied to exact SHAs. Evidence from a prior
candidate cannot be promoted merely because the task name is the same.

## 7. Human authorization is immutable input

Flow Loop Goal issues and owner command comments are rejected when they are edited after creation.
This deliberately chooses auditable immutable authorization over convenient in-place correction.

Correction path: close/reject the old goal and create a fresh one.

## 8. Secrets

Do not commit:

- `policy.json` if it contains environment-specific authority details you do not want reviewed;
- GitHub tokens;
- Codex/ChatGPT auth state;
- `.env` credentials;
- model provider API keys.

FlowAI-Control 0.3.0 does not use an OpenAI API fallback in the supported billing contract.

## 9. Control repo visibility

The current setup path requires a private control repository. That branch contains detailed
engineering state, reports and receipts even when it should contain no ordinary credentials.

Treat it as operational metadata, not as harmless sample output.

## 10. Supply-chain pin

`COMPATIBILITY.json` pins a full controller source SHA. Installation also verifies
`RELEASE-MANIFEST.json` against the exact Git tree and file hashes before copying runtime bytes.

Do not change the pin to `main` or a floating tag merely to make upgrades more convenient.
