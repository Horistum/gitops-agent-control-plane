# Policy

`config/reference-policy.json` is contract v5 policy.

## Actor-specific write envelopes

The developer may write implementation source:

```json
"developer_allowed_paths": ["src/**"]
```

The independent tester may add only diagnostic acceptance-test files:

```json
"tester_allowed_paths": ["tests/test_acceptance_*.py"]
```

Those test files are useful diagnostics but are not the authoritative acceptance channel.

Protected baseline tests are owner-controlled:

```json
"protected_test_paths": ["tests/test_service.py"]
```

Workspace authority/verification infrastructure is snapshotted through:

```json
"authority_paths": [".agent-control/**", "ci/**", ".github/**"]
```

The controller-side `verification-probes.json` is versioned under `.agent-control/`, but v5 intentionally omits it from the candidate workspace and binds its source digest separately in authority/probe evidence.

## Executable quality gates

`quality-gates.json` is not decorative. Contract v5 requires and reads each flag:

- `protect_baseline_test_files`;
- `require_controller_probes`;
- `require_negative_control`;
- `bind_probes_to_exact_git_sha`;
- `require_diagnostic_junit_green`.

Disabling a mandatory gate makes the authority configuration invalid and terminates the run as `BLOCKED_POLICY`.

## Verification definitions

Roadmap acceptance criteria reference product-authored `probe_ids`. The controller resolves those IDs from the controller-side verification definition.

A probe contains:

- target source file;
- callable name;
- runtime case generator;
- case count;
- invariant/oracle kind.

It does **not** contain a public fixed `args` plus literal expected return tuple.

Baseline properties must pass on baseline. New acceptance properties must fail against baseline as a negative control. Candidate and post-merge properties use independently generated fresh cases and must pass against the exact observed Git SHA.

JUnit remains a required green diagnostic in this reference, but it cannot compensate for a failing signed controller probe.

## Receipt policy

The controller creates a fresh HMAC key/challenge per probe and transfers it to the trusted verifier parent through an inherited anonymous control FD. Receipt secrets are forbidden from worker argv/environment. Exactly one HMAC-valid receipt is accepted per probe.

## Structured forbidden paths

The goal contains `forbidden_paths`; product authority contains structured forbidden-path rules. These are executable policy inputs.

Free-form `forbidden_directions`, `authority.md` and `architecture.md` remain explanatory/contextual material included in the authority model. They are not silently interpreted as executable natural-language policy.

## Risk

Risk rules can produce LOW, MEDIUM or HIGH:

- contract paths -> MEDIUM;
- security paths -> HIGH;
- otherwise policy default -> LOW.

`**` matches zero or more complete path segments. Matching is memoized, so repetitive owner-authored patterns do not create exponential recursion.

Owner risk ceiling, automatic-merge ceiling and policy human-gate threshold are independent controls.

## Budgets

Changed-file count and patch bytes are evaluated before candidate workspace mutation. Conformance exercises both independently.

## Execution budget

`test_timeout_seconds` controls wall-clock timeout. The local executor derives its CPU backstop from that value and runs worker/candidate processes in a dedicated process group so descendants are cleaned up.

These controls bound the fixture executor; they do not turn it into a hostile-code sandbox.
