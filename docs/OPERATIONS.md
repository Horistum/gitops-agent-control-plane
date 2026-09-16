# Running and diagnosing the reference

Use Python 3.11+ and Git. Every local execution below uses trusted fixture code.

```bash
./scripts/agentctl help
./scripts/agentctl demo happy-path
./scripts/agentctl loop
./scripts/agentctl validate
```

The loop runs the bundled two-item example. It does not accept a product
repository and ask AI to implement an arbitrary goal. `repair-loop` replays a
prepared correction; it proves feedback transport, not semantic reasoning.

For schema interoperability checks:

```bash
python3 -m pip install -r requirements-test.txt
PYTHONPATH=. python3 tests/test_schema_interoperability.py --require-reference -v
```

Read the emitted run summary and evidence directory. `COMPLETED` refers only to
the machine-evaluated requested item projection. `NEEDS_DECISION` pauses durably;
`BLOCKED_POLICY` and `FAILED_VERIFICATION` require inspecting their recorded
reason. A KNOWN-LIMIT scenario succeeding demonstrates a limitation and is never
reported as a blocked attack.

## operations

Run `./scripts/agentctl loop` for the autonomous showcase. Evidence lives under `.demo/runs/`.

A paused human decision can be resumed with `python3 -S -m reference_runtime.engine --repository-root . --resume .demo/runs/<run-id> --decision approve` (or reject/request_changes).

For analysis inspect run-summary, goal-evaluation, control-loop, state, events, policy/risk/human decisions, feedback, candidate verification, merge, and release-transition evidence.

## linux

The standalone showcase needs only:

- Bash;
- Git;
- Python 3.11+;
- roughly 1 GiB free disk for comfortable experimentation.

Check:

```bash
./scripts/agentctl bootstrap check
```

Prepare supported Debian/Ubuntu or Fedora/RHEL-family systems:

```bash
./scripts/agentctl bootstrap prepare
```

Run:

```bash
./scripts/agentctl validate
./scripts/agentctl demo happy-path
./scripts/agentctl demo all
```

Diagnostics:

```bash
./scripts/agentctl diagnose
```

Remove only local demo artifacts:

```bash
./scripts/agentctl cleanup
```

No daemon, rootless container setup, credentials or external model CLI are required.

## showcase

Run `./scripts/agentctl loop` for the central v7 demo. It selects EXAMPLE-001, verifies/merges it, records controller-owned release state, reconciles, unlocks EXAMPLE-002, carries the first item's acceptance probes forward as regressions, and stops only after both requested items complete.

`repair-loop` demonstrates verification feedback and a second bounded attempt. `human-approve-resume` demonstrates durable human authority. `dependency-blocked` demonstrates refusal to invent undeclared dependency work. All v6 verification/security regressions remain in the matrix.
