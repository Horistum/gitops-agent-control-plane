# Limitations and trade-offs

## Single writer, not consensus

The reference uses one authoritative controller writer. It is appropriate for one active control process with explicit host transfer, not for distributed active-active consensus.

## GitHub-specific lifecycle

The current reference uses GitHub Issues, pull requests, checks and rulesets. The higher-level model is portable, but another Git forge needs an adapter for equivalent primitives and trusted check identity.

## Main branch assumption

The current runtime adapter supports `main` as product base. The portable architecture does not require that name, but this concrete binding does.

## Goal protocol translation

The active backend has a versioned goal/command protocol. The portable interface hides it behind `submit_goal.py` and `control.py`. Changing backends therefore requires adapter updates even when product/goal semantics stay the same.

## Model-provider binding

The concrete adapter expects a specific authenticated model CLI contract. The reference does not claim billing/authentication behavior is portable. What is portable is the requirement that provider identity and fallback behavior be explicit.

## Test image responsibility

The reference deliberately does not ship a magic universal build image. Product teams must create and pin an image containing their deterministic build/test toolchain. A fake digest would make the sample look easier while teaching the wrong trust model.

## Repository governance privileges

Creating repository rulesets may require administrative privileges or a plan/configuration supporting the relevant API. The helper refuses to silently overwrite existing governance.

## Public distribution

A technically reusable repository is not automatically a legally reusable public project. Publication requires explicit visibility, licensing and contribution/security policy decisions.

## No claim of autonomous architecture invention

The controller can reason about architecture, but authoritative architecture and acceptance must exist in the product repository. The reference optimizes autonomous execution of bounded intent; vague product strategy does not become safe merely because a stronger model is selected.

## Cost and latency

Multiple independent roles, deterministic baselines and exact-SHA CI cost more than a single prompt. That is deliberate: the system spends compute to buy evidence and reduce human handoffs. Adaptive graphs and bounded context keep that cost finite.
