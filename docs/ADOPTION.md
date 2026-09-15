# Adapting the reference

Treat the repository as a composition of a core control-plane contract plus replaceable verification/runtime profiles. Do not start by wiring an LLM to the local executor and hoping the surrounding invariants somehow materialize. Humans have tried this general technique with distributed systems too, with memorable results.

## 1. Classify authority first

Before connecting a reasoning provider, identify which product artifacts are:

- intent authority;
- state authority;
- change authority;
- verification authority;
- reasoning context.

The reference `.agent-control/authority-model.json` is a product-owned authority manifest. Adaptations may use other artifact names, but the core invariant remains: reasoning cannot silently convert context into machine policy or take ownership of controller state.

## 2. Define goal semantics honestly

Classify each goal field according to what the controller actually does with it. In v1, `items`, risk/merge/autonomy bounds, and forbidden paths are machine enforced. `objective`, `success_condition`, and `forbidden_directions` are reasoning context.

If a product needs an executable success predicate beyond completion of authorized roadmap items, define a typed predicate contract or a new core profile. Do not label prose as verified merely because an evidence artifact repeats it.

## 3. Bind roles to real authority

`config/role-protocols.json` is active in the reference runtime. Proposal-producing roles resolve `product_write_power` to concrete policy path envelopes; roles with `none` cannot submit product changes. No role receives Git effect power.

For another system, preserve that separation even if role names differ. A model may propose a patch, a test, or a plan, but the controller applies policy and owns side effects.

## 4. Choose a verification profile

`property-probe/v6` supports multiple positional args, generated named kwargs, bounded generators, exception or return-equality oracles, and a generic expression language. Static validation rejects references to nonexistent args/kwargs, incompatible `length` operands, and expressions deeper than the supported bound before candidate execution begins.

The DSL is intentionally limited. If a product needs richer invariants, extend or replace the verification profile rather than embedding product-specific Python callbacks in the generic control plane.

## 5. Choose a runtime profile

`standalone-local/v2` uses local Git and trusted deterministic fixture processes. It demonstrates effect identity, resume semantics, bounded process execution, and conformance mechanics. It is not a hostile-code sandbox.

A production runtime for model-generated arbitrary code needs stronger isolation such as container, VM, or remote verification boundaries and a result channel outside candidate control.

## 6. Preserve revision identity

Human and automatic effects should name exact immutable revisions. A human approval is valid only for the reviewed SHA. The reference re-resolves the mutable candidate branch before approval, performs an exact-SHA merge, verifies both merge parents, and retains candidate commits under audit refs even when working branches are deleted.

Production GitHub/GitLab adapters should preserve the same property using provider-native compare-and-swap or protected-ref mechanisms.

## 7. Re-run preconditions on repair

Persist verification feedback and route bounded repair attempts, but never assume old preconditions apply to a new base revision. After `request_changes`, rerun baseline verification, completed-item regressions, and acceptance negative control before the next proposal attempt.

## 8. Reconcile after every verified effect

Make human approve/reject/request_changes resumable. Make both product merge and controller progress updates durable effects. After every verified progress transition, reload authority/release state and reconcile until the requested objective projection is satisfied or authority is exhausted.

## 9. Keep evidence auditable

Evidence that names a candidate SHA should retain that Git object. Negative fixtures should remain readable enough that a reviewer can verify the attack path without mentally unescaping a thousand-character source literal. Schema coverage and conformance assertions should prove properties, not merely count files.
