# Reasoning-role model

The reference separates roles, but the roles in this repository are deterministic fixtures rather than production AI agents.

## Write domains

- Discovery and architect produce no product edits.
- Developer proposes implementation source only.
- Independent test designer proposes only new acceptance-test files.
- Reviewer writes no product content and computes its verdict from controller evidence.

The developer therefore cannot write its own acceptance criteria or replace protected baseline tests.

## Computed reviewer

`review.json` is not a set of hard-coded `true` literals. It is computed from:

- authority snapshot presence and equality;
- path-policy decisions;
- candidate process result;
- candidate SHA/tested SHA equality;
- protected baseline file digest;
- baseline test identity preservation;
- roadmap-required acceptance identities;
- minimum candidate test count.

Any failed predicate becomes a blocking finding.

## Production model integration boundary

Replacing deterministic proposal fixtures with an AI model is not just a different function call. The standalone local executor is explicitly not a security sandbox and the runtime refuses non-fixture proposal sources.

A production integration needs a sandboxed execution adapter plus the same authority/evidence invariants.
