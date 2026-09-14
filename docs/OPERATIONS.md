# Operations

Run `./scripts/agentctl loop` for the autonomous showcase. Evidence lives under `.demo/runs/`.

A paused human decision can be resumed with `python3 -S -m reference_runtime.engine --repository-root . --resume .demo/runs/<run-id> --decision approve` (or reject/request_changes).

For analysis inspect run-summary, goal-evaluation, control-loop, state, events, policy/risk/human decisions, feedback, candidate verification, merge, and release-transition evidence.
