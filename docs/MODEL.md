# Reasoning-role model

The reference separates roles, but the roles in this repository are deterministic fixtures rather than production AI agents.

## Write domains

- Discovery and architect produce no product edits.
- Developer proposes implementation source only.
- Independent test designer may propose diagnostic acceptance-test files only.
- Reviewer writes no product content and computes its verdict from controller evidence.

The developer cannot replace product-authored verification probes, product authority or protected baseline tests.

## Test-designer role is not the root of trust

A test designer can make diagnostics more useful, but its Python test file executes in a process that also imports candidate code. Contract v4 therefore does not treat tester-authored JUnit identities or counts as proof of behavior.

Acceptance authority comes from product-authored structured probes. The controller executes them and records completion receipts. The tester role may explain or supplement that evidence, but cannot mint it.

## Computed reviewer

`review.json` is computed from:

- authority snapshot presence/equality;
- path-policy decisions;
- protected baseline file digest;
- baseline acceptance negative control;
- controller probe completion/pass state;
- exact candidate-SHA probe binding;
- supplemental diagnostic JUnit result.

A green diagnostic suite cannot compensate for a failed controller probe.

## Production model integration boundary

Replacing deterministic proposal fixtures with an AI model is not just a different function call. The standalone local executor and probe worker are explicitly not complete security sandboxes and the runtime refuses non-fixture proposal sources.

A production integration needs an isolated execution/verifier adapter whose result channel is outside the candidate's control, while preserving the same product authority, exact identity, risk and durable-effect invariants.
