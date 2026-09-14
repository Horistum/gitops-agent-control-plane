# Public adoption readiness

The reference implementation can be technically correct while still not be publicly consumable. Those are different problems, and this project should not confuse them.

## Desired publication model

A public Horistum distribution should expose:

1. a **public reference/template repository** containing documentation, scaffolding and examples;
2. a **publicly retrievable, versioned FlowAI-Control runtime source or release artifact**;
3. a documented compatibility matrix binding each reference revision to an exact runtime release;
4. a clear software license for every published repository/artifact.

Each adopter should then create its **own private tenant control repository** from the public reference. The tenant repository contains operational state, task reports, Goal authorizations and execution receipts, so it should not be treated as harmless public sample data.

## Current blockers

At the time of this reference revision:

- `Horistum/FlowAi-control` is private;
- `Horistum/gitops-agent-control-plane` is private;
- the pinned FlowAI-Control source does not contain a standard `LICENSE` or `LICENSE.md` file;
- FlowAI-Control 0.3.0's upstream upgrade helper still contains the original pilot assumption that runtime source and control/state repository are the same repository.

The reference installer works around the last item safely by installing the exact pinned runtime source directly. It cannot, and should not, work around repository visibility or licensing.

## Publication checklist

Before describing the project as publicly adoptable, complete all of the following:

- [ ] Choose and review the license for FlowAI-Control.
- [ ] Choose and review the license for this reference repository.
- [ ] Publish FlowAI-Control source or an equivalent immutable release artifact that external adopters can retrieve without Horistum-private GitHub access.
- [ ] Publish this reference repository as a template/reference repository.
- [ ] Keep documentation explicit that the adopter's generated/copied control repo is private even though the template is public.
- [ ] Tag or otherwise version the compatible FlowAI-Control release and keep `COMPATIBILITY.json` pinned to immutable identity.
- [ ] Validate a clean-room install from an account that has no private Horistum repository access.
- [ ] Validate product ruleset creation and GitHub Actions check identity on the GitHub plans intended for supported users.
- [ ] Document supported Linux distributions, Podman versions and Codex CLI versions.
- [ ] Add vulnerability/security reporting guidance before inviting untrusted external users.
- [ ] Decide whether releases are source-only or also provide signed packages/container artifacts and document verification accordingly.

## Clean-room acceptance test

Public readiness should be proven from a fresh external account and machine, not inferred from the Horistum maintainer environment.

A passing clean-room test should demonstrate:

1. clone/download of the public reference;
2. creation of a new private tenant control repository;
3. creation of the minimal product repository;
4. successful baseline CI;
5. policy rendering with no Horistum-internal identifiers except the public runtime release reference;
6. successful governance preflight;
7. installation and integrity verification of the pinned runtime;
8. `flow_loop doctor` success;
9. explicit owner activation;
10. acceptance of a `DEMO-001` Goal Issue;
11. autonomous candidate creation, trusted CI, merge and post-merge evidence;
12. final `loop-state` audit success.

Only after that sequence passes should the example be described as a public zero-to-working reference rather than merely an internal reference implementation.
