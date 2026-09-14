# Policy

`config/reference-policy.json` is contract v6 policy.

## Write envelopes

Developer writes implementation source only. Tester writes diagnostic acceptance files only. Protected baseline tests and authority/CI paths remain outside both proposal envelopes.

Candidate-process tests are diagnostics, not the authoritative acceptance channel.

## Executable quality gates

`quality-gates.json` is runtime input. Mandatory gates protect baseline files, require controller probes, require case-level negative control, bind probes to exact Git SHA and require green diagnostic JUnit. Disabling a mandatory gate is invalid authority and fails closed.

## Generic verification definitions

Roadmap acceptance criteria reference product-owned `probe_ids`. The controller resolves them from the controller-side verification definition, whose source digest is evidence-bound but whose file is omitted from the candidate workspace.

A v6 probe declares target/callable, case count, positional `args` generators, named `kwargs` generators and a generic oracle. The reusable DSL supports constants, choices, primitive/random values, token/whitespace generation and expression composition. Product-specific oracle code does not live in the control plane.

Regression probes must pass on baseline. For new acceptance behavior, **every generated acceptance case** must fail on baseline. Candidate and post-merge probes use fresh independently generated cases and must pass on the exact observed SHA.

## Receipt policy

The controller creates a fresh HMAC key/challenge and supplies the trusted verifier parent through an inherited control pipe. The executor starts the reader before writing payload bytes. The parent closes the control FD before candidate execution and emits exactly one signed receipt. Candidate-child stdout is untrusted observation and cannot become the final parent receipt stream.

## Structured forbidden paths, risk and budgets

Goal/authority forbidden paths are executable structured inputs. Human-readable prose remains context.

Risk rules produce LOW/MEDIUM/HIGH with independent goal ceiling, auto-merge ceiling and human-gate threshold. Changed-file and patch-byte budgets run before candidate mutation.

Path matching is segment-aware and memoized. `**` matches zero or more segments with O(P*L) memoized states rather than exponential backtracking.

## Execution boundary

`test_timeout_seconds` controls wall-clock execution, with CPU backstop and process-group cleanup derived from policy. These are bounded-execution controls, not a hostile-code sandbox.
