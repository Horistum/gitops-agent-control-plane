# Verification

## Repository validation

```bash
./scripts/agentctl validate
```

Checks:

- internal/project branding does not leak into the reference;
- JSON documents parse;
- portable contracts validate semantically;
- JSON Schema documents use Draft 2020-12;
- authority files exist and stay outside the write envelope;
- Python parses;
- Bash entrypoints pass `bash -n`;
- Linux bootstrap pure self-test passes;
- the example baseline executes three real tests;
- the complete five-scenario conformance matrix passes.

## Conformance matrix

```bash
./scripts/agentctl conformance
```

This executes real temporary Git repositories and real product tests.

It proves behavior of the standalone reference runtime, including negative gates and recovery.

## CI

GitHub Actions runs the same validation on every pull request and on `main`, then runs another preserved happy-path demo so the lifecycle is visible in CI logs.

## What it does not prove

The standalone reference intentionally does not contact an external model, Git host or CI provider.

It demonstrates the control-plane invariants those integrations must preserve.
