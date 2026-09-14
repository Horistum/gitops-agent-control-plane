# Limitations

The reference is executable but is not a production autonomous-engineering runtime.

## No complete hostile-code boundary

Contract v6 keeps receipt secrets out of candidate protocol inputs, separates verifier parent from candidate child and blocks candidate final-receipt injection. Candidate Python still runs on the same host. A malicious same-user process may attempt `/proc`, file-descriptor, filesystem, kernel or other attacks outside the fixture protocol.

Production hostile-code verification therefore requires a container, VM or remote verifier with independently protected internals/result channel.

## Generated invariants are finite tests

Fresh generated cases reduce simple lookup-table overfitting, but they are not formal proof. Products should combine properties with deterministic regressions, static/domain-specific checks and stronger methods where appropriate.

V6 improves negative-control semantics by requiring every generated acceptance case to fail on baseline. That proves the sampled cases distinguish the new criterion; it still says nothing about unsampled inputs.

## Candidate raw outcomes are an executable KNOWN-LIMIT

A candidate child reports return/exception information through captured stdout. The verifier parent evaluates those observations and produces the signed receipt. Because the trusted `probe_child.py` wrapper imports candidate Python in the same interpreter, malicious candidate code can inspect wrapper frames, discover the current input/callable, emit its own `REFERENCE_RAW_OUTCOME=...`, and terminate before the wrapper emits the genuine observation.

The `raw-outcome-forgery` conformance scenario reproduces this **KNOWN-LIMIT** deliberately. It verifies that:

- the candidate's public diagnostic tests remain green;
- the candidate's direct unicode behavior is wrong;
- every candidate probe observation carries a `candidate_forged: true` marker originating in candidate code;
- the verifier parent accepts those forged raw observations and signs otherwise-valid receipts;
- the candidate can therefore reach merge/completion inside the standalone same-host fixture model.

This scenario is reported as `KNOWN-LIMIT`, not as an enforced security property. If the raw channel is hardened later, the scenario must be changed to an enforced negative case and expected to block.

The limitation is precisely why parent HMAC signing is not equivalent to hostile-code evidence integrity: HMAC authenticates what the parent decided, but the parent can still be fed a forged observation below its trust boundary.

## Generic DSL is deliberately bounded

The v6 DSL supports multiple args, kwargs, several primitive generators and a small expression language. It cannot express arbitrary temporal behavior, stateful protocols, filesystem/network effects, custom comparators or every product domain without extension.

New reusable semantics should be added as validated generic DSL operations with schemas/conformance. Embedding product-specific Python oracle functions in the control plane would defeat the portability goal.

## Verification definition is not secret

`verification-probes.json` is omitted from the candidate workspace but remains versioned repository content. Security relies on runtime-generated inputs and verifier authority, not on pretending the definition is confidential.

## JUnit and event-chain boundaries

JUnit remains diagnostic only. The event chain provides consistency, not authenticity against complete evidence-store rewriting.

## Reference roles

Deterministic fixtures demonstrate controller behavior rather than model capability. Replacing them with AI requires stronger execution isolation while preserving the same authority/evidence semantics.
