# Adapting the reference

Start with authority, oracle strength and verifier trust boundaries before connecting a model.

## Product authority

Create product-owned roadmap, release state, forbidden rules, quality gates and verification definitions outside the implementation write envelope. Prefer not to copy verifier definitions into the candidate workspace.

## Use the generic invariant DSL

Contract v6 is deliberately product-neutral. A product can define probes without patching the control plane by composing a small **generic** DSL:

- multiple positional `args` generators;
- named `kwargs` generators;
- constants, choices, booleans, integers, whitespace and token-text generators;
- `raises` or `return-equals` oracles;
- expression nodes for `arg`, `kwarg`, literal, concat, split-whitespace, join, lower/upper, strip and length.

This is intentionally less powerful than arbitrary executable verifier code. If a product needs semantics the DSL cannot represent, extend the public DSL deliberately with validation, schemas and conformance rather than hiding product-specific Python inside the controller.

## Define properties, not only examples

Public fixed examples are useful diagnostics but easy to overfit. Where possible, describe generators and invariants and create fresh inputs during verification. Keep deterministic regressions too.

For new behavior, the baseline negative control should demonstrate real discrimination: **every generated acceptance case** must fail on baseline, not merely one case in an aggregate probe.

## Separate verifier judgment from candidate observation

A useful pattern is:

```text
controller
  -> private control channel
trusted verifier parent
  -> current args/kwargs only
candidate child
  -> untrusted return/exception/stdout observation
trusted verifier parent
  -> generic invariant evaluation + authenticated receipt
controller
```

Candidate stdout must not become the final receipt stream. Conformance should prove current attack paths actually execute instead of assigning security labels to dead fixtures.

## Bind evidence to exact identities

Record candidate/merge SHA, verifier-definition digest, probe ID and authenticated receipt identity. A green result without exact revision/verifier identity is incomplete evidence.

## Production isolation

The standalone fixture boundary is not adequate for arbitrary hostile/model-generated code. Use a container, VM or remote verifier whose process/filesystem and result channel are outside candidate control.

## Preserve risk and effect authority

Successful verification is not permission to cross a security/contract/migration boundary. Persist stable identities before non-idempotent effects and recover by discovering whether that exact effect already occurred.

## Add AI last

Only replace deterministic role producers with a model after authority enforcement, verifier trust, exact identity and durable effect handling work without it.
