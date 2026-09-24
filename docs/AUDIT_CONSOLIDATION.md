# Audit consolidation: retained semantics and removed duplicates

This change consolidates implementation paths without adding a second controller,
a database, a new approval mechanism or automatic budget resets. The complete
merge-receipt protocol and deterministic trusted-check evaluator are documented
separately in `MERGE_RECEIPT_RECOVERY.md` and `TRUSTED_CHECK_EVALUATION.md`.

## Scenario requests

`scenarios.build_request_from_spec` is the single pure builder used by the
file/name entry point and the in-process conformance path. Both preserve the
original `goal.success_condition` reasoning context. Explicit non-empty
`goal_items` select scenario scope; absent items use `EXAMPLE-001` independently
of the scenario name. Invalid empty or non-list explicit items are rejected.
Existing schema-validated fixtures keep their machine goal and work catalog.
Neither the base goal nor the scenario input is mutated.

## Evidence validation

`_schema_validation_impl.validate_evidence_directory` accepts explicit artifact
registries. The public wrapper forwards its superset of named schemas and
patterns instead of maintaining a second loop. Exact names take precedence,
pattern matches retain their declared order, discovered files retain sorted
order, and event JSONL validation remains last. Passing empty registries is
intentional and does not accidentally select the defaults. Public recovery
artifact extensions remain mandatory when those artifacts exist.

## Recovery projections

`agent_runtime.recovery.task_recovery` maps the same operational state to the
shared core for status, decision projection and the actual retry command. It
passes the configured context limit, lifetime model-call usage, pending effect,
recorded owner replan count and current failure code. The shared core recognizes
`CONTEXT_LIMIT` as exhaustion in addition to the existing consumer codes.

The controller's independent `retryable=False` policy hold remains in place.
Retry does not clear context rounds or reset lifetime usage. Missing context
limits in minimal read-only legacy projections use the existing core default;
validated production policies explicitly provide the configured limit. This
mapping does not widen owner replan eligibility for running tasks or replace the
separate pending-effect, approval, drift and retirement checks. It makes held
status accurately reflect an already exhausted owner replan count.

## Removed scaffolding

The uncalled selector and unprefixed merge lifecycle on internal `BaseEngine`
have been removed. The final-trailer regression now exercises the live
`LocalGitEffectAdapter.find_trailer_effect` implementation. Public composed
engine entry points and adapter protocols are unchanged.

The unreachable inner `EXHAUSTED` result and its handler are removed from the
candidate-attempt implementation. The outer bounded loop still owns catalog
exhaustion and attempt-budget exhaustion, preserving their distinct reasons.

## Intentionally unchanged

`GitRepository.refresh_base` still creates a candidate checkpoint with parents
`[head, new_base]`. This is not the final merge receipt, whose ordered parents
must be `[base, candidate]`. An inline comment explains the difference; existing
base-refresh replay and approval-invalidation coverage is retained. Secret
redaction rules are unchanged, including short explicit credential masking and
preservation of operational identifiers under heuristic environment inference.

Tests cover complete request equality across the scenario catalog, original
prose and input preservation, registry forwarding and precedence, invalid
recovery evidence, empty/bounded catalogs, the live final-trailer parser, and
status/decision/command agreement on non-default context limits and real
context-limit holds. Run the complete validation and publication checks before
merging; this document is not a replacement for their results.
