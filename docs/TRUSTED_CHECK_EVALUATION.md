# Deterministic trusted-check evaluation

`control_plane_core.evaluate_trusted_checks(required, observed)` is the single
classifier used by the GitHub adapter and the existing `trusted_checks_pass`
boolean API. Its `status`, `passed` and `failed` fields come from the same
normalized observations. The adapter still requires the exact Git revision and
the owner-declared check name and provider application ID.

The states are `success`, `failure`, `pending`, `conflict` and `invalid`. Only
`success` has `passed=true`; only `failure` has `failed=true`. The current strict
policy is unchanged for completed non-success conclusions, including `neutral`
and `skipped`: they do not satisfy a required successful check. A completed
observation with no conclusion is malformed rather than evidence for a code
repair. Missing or unfinished required checks remain pending.

For each required name/provider pair, the highest numeric check ID is the latest
run. Repeated identical observations are harmless. Differently worded rows for
the same identity conflict, including conflicts on an older ID accompanied by a
newer successful run. Malformed required observations take precedence over
conflicts, then conflicts over reported failures. Classification is independent
of row ordering and does not mutate caller inputs.

Conflicts and invalid evidence cannot authorize a merge or completion and do not
trigger model-driven code repairs. The controller retains the observed check
state and waits for a fresh observation. Genuine non-success CI continues to
use the existing bounded repair and post-merge hold behavior. The classifier
does not authenticate a provider or weaken the separate repository governance,
revision identity or approval gates.

Regression tests permute current/older conflicting IDs, identical duplicates,
invalid rows, newer reruns and wrong providers. They also exercise both candidate
and post-merge lifecycle paths and verify that conflicts never invoke `repair`
or the failed-CI hold path. No live GitHub service or model calls are required.
