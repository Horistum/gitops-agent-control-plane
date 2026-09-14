# Verification matrix

The reference distinguishes **offline contract verification**, **host/runtime verification** and **live delivery verification**. All three matter, and none should be mislabeled as the others.

## Layer A: repository CI

Run:

```bash
./scripts/agentctl validate
```

Equivalent direct command:

```bash
python3 scripts/validate_reference.py
```

The suite verifies:

| Check | Proof |
|---|---|
| Example baseline | executes the real product test runner |
| Test discovery | requires executed tests |
| JUnit evidence | parses generated XML and requires unique testcase identities |
| Portable authority layout | requires `.agent-control/*` files and keeps them outside write paths |
| Policy renderer | renders a complete tenant policy in a temporary directory |
| Policy identity | confirms product/control separation and CI identity consistency |
| Goal adapter | builds backend protocol from portable goal JSON without GitHub writes |
| Operator adapter | maps every generic owner command to one exact backend message |
| Governance renderer | validates ruleset structure and trusted check binding |
| Compatibility pin | requires an exact runtime commit |
| Python syntax | compiles reference scripts and example code |
| Linux Bash syntax | `bash -n` checks every shipped shell entry point |
| Linux bootstrap logic | pure self-test exercises supported distribution/package-manager mapping |
| Bash wrapper contract | `agentctl` self-test verifies expected entry points |
| Diagnostic/uninstall CLI | help paths execute without mutation |
| Backend-neutral narrative | rejects concrete backend branding in README and portable docs |

GitHub Actions runs these checks on every pull request and on `main`.

Layer A does **not** prove a live model, GitHub mutation, container runtime on another machine or a future adopter's credentials.

## Layer B: Linux host and runtime-adapter preflight

First run:

```bash
./scripts/agentctl bootstrap check
```

Then install/prove the runtime adapter:

```bash
./scripts/agentctl install --policy policy.json
```

The live host path verifies supported/unprivileged Linux execution, required commands and user systemd availability, rootless Podman, minimum free disk, repository access and product/control separation, private control repository and enabled Issues, default branch and command issue, exact pinned runtime commit, runtime Git tree versus release manifest, SHA-256 of manifest files, absence of extra files in an existing immutable runtime installation, runtime unit tests and doctor/preflight, exact model/runtime CLI identity expected by policy, real model protocol smoke unless explicitly skipped, real isolated product baseline unless explicitly skipped and installed user service state.

Skip flags in the Python installer exist for diagnosis. A skipped proof must not be represented as a completed proof.

Read-only diagnostics are available through:

```bash
./scripts/agentctl diagnose --policy policy.json
```

## Layer C: first live goal

The first live goal proves the lifecycle static CI and host preflight cannot:

1. portable owner goal translated and accepted;
2. `EXAMPLE-001` discovered from product authority;
3. bounded candidate implementation created;
4. deterministic tests execute and produce identities;
5. independent test/review evidence exists;
6. product pull request is created for the exact candidate SHA;
7. trusted CI succeeds for that candidate;
8. merge occurs only under configured authority;
9. trusted post-merge CI succeeds on the exact merge SHA;
10. completion is persisted in remote authoritative state.

The example is intentionally small so every artifact can be manually inspected.

## Layer D: production adaptation

A production repository requires another proof cycle after replacing the example policy/authority model.

At minimum re-prove real architecture/forbidden paths, production build/test commands, CI integration IDs/check names, critical/public/security path classification, risk thresholds and owner boundaries, context/cost/time budgets, rollback/recovery procedures, single-writer migration behavior and representative low/medium/high-risk scenarios.

Passing the example is evidence that the reference mechanism works. It is not evidence that a different production repository has been modeled correctly.

## What a green badge means

A green `Reference integrity` badge means the **repository contract is internally executable and consistent**.

A successful runtime install means the **specific host and pinned adapter passed live preflight**.

A completed first goal means the **reference delivery lifecycle was exercised end to end**.

Those are intentionally separate statements. Compressing them into a single vague “works” claim would make the README shorter and the evidence worse.
