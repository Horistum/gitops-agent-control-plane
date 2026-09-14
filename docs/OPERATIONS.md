# Operations

The reference has one operator surface:

```bash
./scripts/agentctl help
```

The standalone mode deliberately has no long-running daemon. Each run is isolated under `.demo/runs/`.

## Run retention

Keep a run directory when you want to inspect evidence. Remove all local demo artifacts with:

```bash
./scripts/agentctl cleanup
```

## Failure analysis

For a blocked or failed scenario, inspect in this order:

1. `run-summary.json`;
2. `state.json`;
3. `events.jsonl`;
4. `policy-decision.json` or `risk-decision.json`;
5. candidate/test/review evidence.

The evidence tree is designed so the terminal state is explainable without reading controller source first.
