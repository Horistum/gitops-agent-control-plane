# GitOps Agent Control Plane Reference

A runtime-neutral reference architecture for **bounded autonomous software delivery through Git**.

The repository answers a practical question: if an engineering agent is allowed to propose and deliver changes with minimal human intervention, what must exist around the model so the result remains reviewable, reproducible, recoverable and safe?

This is deliberately not documentation for one product or one model provider. The reference separates portable control-plane concepts from a replaceable runtime adapter. You can keep the architecture, policy model, product authority files, evidence rules and GitHub operating model while replacing the controller implementation underneath them.

## What the reference demonstrates

The example implements a complete bounded-delivery model:

1. an owner defines a **goal** and an explicit authority envelope;
2. the controller discovers one eligible work item from product-authored roadmap data;
3. independent roles plan, implement, test and review the change;
4. deterministic tests run outside the model session;
5. GitHub CI must prove the exact candidate commit;
6. merge authority is evaluated from risk, critical paths and policy;
7. post-merge verification proves the exact merge commit;
8. every durable state transition and external effect has auditable evidence.

The human is not replaced by a long prompt. Human authority is converted into explicit, machine-checkable boundaries. A language model can reason inside those boundaries, but cannot redefine them merely because doing so would make the task easier.

## Portable architecture

The design has four distinct authorities:

| Authority | Owns | Must not own |
|---|---|---|
| **Product repository** | source, tests, roadmap, architecture and acceptance criteria | controller state or model credentials |
| **Control repository** | owner commands, goal intake and remote execution state | product source |
| **Runtime adapter** | orchestration, role execution, policy enforcement and effect handling | product intent |
| **External verifiers** | CI/check results tied to exact SHAs | authority to rewrite goals |

Keeping these separate prevents the controller from becoming both the thing being changed and the authority deciding whether the change was valid.

## Repository map

| Path | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | components, trust boundaries, state and data flow |
| `docs/MODEL.md` | role graph, model contract, context retrieval and evidence |
| `docs/POLICY.md` | authority envelope and configuration semantics |
| `docs/ADOPTION.md` | clean installation and first end-to-end run |
| `docs/LINUX.md` | Linux host bootstrap, service lifecycle, diagnostics and uninstall |
| `docs/OPERATIONS.md` | normal operation, recovery and human interventions |
| `docs/SECURITY.md` | threat model and fail-closed design |
| `docs/PORTABILITY.md` | what is portable and what belongs to a runtime adapter |
| `docs/VERIFICATION.md` | exactly what is tested and what still requires live proof |
| `docs/LIMITATIONS.md` | explicit constraints and unresolved trade-offs |
| `examples/minimal-product/` | deliberately small product with one unfinished roadmap item |
| `examples/goal.example.json` | portable goal input used by the first-run scenario |
| `config/policy.template.json` | complete policy example |
| `scripts/agentctl` | single Linux/operator entry point |
| `scripts/bootstrap-linux.sh` | Linux prerequisite check/provisioning |
| `scripts/diagnose-linux.sh` | read-only host/service diagnostics |
| `scripts/uninstall-linux.sh` | safe local service/runtime cleanup |
| `scripts/render_policy.py` | renders tenant-specific policy without modifying the template |
| `scripts/submit_goal.py` | translates a portable goal into the active runtime protocol |
| `scripts/control.py` | runtime-neutral operator commands |
| `scripts/product_governance.py` | validates/applies required GitHub product governance |
| `scripts/install_runtime.py` | installs and proves the pinned runtime adapter |
| `scripts/validate_reference.py` | offline reference integrity suite |

## Reference scenario

The runnable example starts green. `normalize_name()` is already implemented and tested. Roadmap item `EXAMPLE-001` asks the agent system to add a small `greet()` API without changing CI, architecture or existing normalization semantics.

That small change is intentional. It is large enough to exercise discovery, planning, implementation, independent tests, review, candidate CI, merge and post-merge verification, while remaining small enough that a human can inspect every artifact and know whether the automation is telling the truth.

Run the local reference checks first:

```bash
./scripts/agentctl validate
```

Expected result includes a real execution of the example product tests and a generated JUnit report. No model, GitHub write or external service is required for this offline check.

## Linux quick start

On Debian/Ubuntu or Fedora/RHEL-family Linux:

```bash
./scripts/agentctl bootstrap check
./scripts/agentctl bootstrap prepare
./scripts/agentctl validate
```

Then follow `docs/ADOPTION.md` to create separate product/control repositories and render the tenant policy. Once `policy.json`, the deterministic test image and runtime/model authentication are ready:

```bash
./scripts/agentctl governance --policy policy.json
./scripts/agentctl governance --policy policy.json --apply
./scripts/agentctl install --policy policy.json

./scripts/agentctl control --policy policy.json \
  activate --fingerprint <PRINTED_FINGERPRINT>

./scripts/agentctl goal --policy policy.json \
  --file examples/goal.example.json
```

For host-level troubleshooting:

```bash
./scripts/agentctl diagnose --policy policy.json
```

The detailed Linux runbook, including rootless Podman, systemd user services, safe uninstall and host migration boundaries, is in `docs/LINUX.md`.

## First live run

The controller should select `EXAMPLE-001`, create a candidate, run deterministic verification, publish a pull request, wait for the trusted check identity and continue according to configured risk/merge authority.

The portable owner surface is intentionally narrow:

```bash
./scripts/agentctl control --policy policy.json pause
./scripts/agentctl control --policy policy.json drain
./scripts/agentctl control --policy policy.json resume
./scripts/agentctl control --policy policy.json refresh
```

Approval, retry, replan and cancellation require the exact task/goal identity and hash shown by the control plane. Backend-specific comment syntax remains an implementation detail inside the runtime adapter.

## Design principles

- **single writer** for authoritative execution state;
- **immutable effect identity** for crash recovery;
- **exact SHA evidence**, never “the latest build looked green”;
- **model proposals are not execution evidence**;
- **authority documents are product-authored and outside the agent write envelope**;
- **critical paths cannot silently auto-merge**;
- **runtime changes require explicit re-activation**;
- **all external mutations are narrower than the model's reasoning scope**;
- **no hidden fallback from a failed hard gate to a more convenient interpretation**.

## Verification status

The CI-safe layer runs on every PR and proves the portable reference itself: example tests, JUnit evidence, policy rendering, goal translation, operator command translation, governance payload shape, Linux shell syntax/self-tests and cross-file consistency.

The live layer runs on a real controller host and additionally proves credentials, container isolation, pinned runtime, model protocol, product baseline and GitHub lifecycle.

See `docs/VERIFICATION.md` for the exact matrix. A green unit test is useful; pretending it proved an external system that was never contacted is not.
