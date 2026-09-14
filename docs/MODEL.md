# Reasoning-role model

The reference separates roles, but the roles in this repository are deterministic fixtures rather than production AI agents.

## Write domains

- Discovery and architect produce no product edits.
- Developer proposes implementation source only.
- Independent test designer may propose diagnostic acceptance-test files only.
- Reviewer writes no product content and computes its verdict from controller evidence.

The developer cannot replace product-authored authority or protected baseline tests. Contract v5 additionally omits the verifier definition from the candidate workspace.

## Test-designer role is not the root of trust

A test designer can make diagnostics more useful, but its Python test file executes in a process that also imports candidate code. Contract v5 therefore does not treat tester-authored JUnit identities or counts as proof of behavior.

Acceptance authority comes from product-authored **generator + invariant** definitions evaluated by a trusted verifier parent. The test-designer role may explain or supplement that evidence, but cannot mint the HMAC-authenticated parent receipt.

## Candidate child is not the verifier

The candidate child receives only the current generated input and produces a raw return/exception observation. It does not receive the receipt HMAC key, challenge, private oracle or future generated cases through the normal protocol.

The trusted verifier parent never imports candidate code. It owns case generation, oracle evaluation and the final signed receipt.

This separation prevents the previous mistake where the code being evaluated could read a receipt nonce from its own argv and manufacture a controller-looking success artifact.

## Computed reviewer

`review.json` is computed from:

- authority snapshot presence/equality;
- controller-side verifier-definition digest;
- path-policy decisions;
- protected baseline file digest;
- generated baseline acceptance negative control;
- HMAC-validated controller probe completion/pass state;
- exact candidate-SHA probe binding;
- supplemental diagnostic JUnit result.

A green diagnostic suite cannot compensate for a failed controller probe.

## Oracle strength

The verifier definition contains property generators and invariants instead of fixed public examples. This makes a candidate that simply hardcodes published fixture values insufficient.

The `probe-aware` scenario proves this. Its implementation passes the classic public `Ada Lovelace` diagnostic but fails fresh runtime-generated greeting cases.

Randomized tests remain finite samples rather than formal proof.

## Production model integration boundary

Replacing deterministic proposal fixtures with an AI model is not just a different function call. The standalone local executor/verifier is explicitly not a complete hostile-code security boundary and the runtime refuses non-fixture proposal sources.

A production integration needs an isolated execution/verifier adapter whose result channel is outside the candidate's control, while preserving product authority, generated-oracle semantics, exact identity, risk and durable-effect invariants.
