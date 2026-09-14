# Minimal FlowAI-Control product

This directory is a copyable product repository, not a toy pseudo-configuration. Its initial `main`
is green, while roadmap item `DEMO-001` asks FlowAI-Control to add one small feature.

## What to copy

Create a separate GitHub repository and copy the **contents** of this directory to its root. Keep
`main` as the default branch. Do not place this directory inside the control repository in production.

The example deliberately keeps owner-controlled CI under `ci/` and `.github/workflows/`. The
reference policy does not allow product agents to edit either path.

## Baseline

Run:

```bash
python3 ci/run_tests.py
```

The command writes JUnit XML to `build/test-results/reference/TEST-reference.xml`, because
FlowAI-Control 0.3.0 requires observed JUnit identities rather than trusting exit code zero alone.

## First autonomous goal

After the controller is installed and activated, create a **Flow Loop goal** in the control
repository for `DEMO-001`. The current code intentionally does not implement `greet`; the roadmap
defines the desired result and acceptance criteria. The baseline still passes before the change.
