# Policy

`config/reference-policy.json` defines the bounded authority used by the standalone showcase.

## Write envelope

```json
"allowed_paths": ["src/**", "tests/**"]
```

Implementation may change source and tests.

## Owner-controlled authority

```json
"authority_paths": [".agent-control/**", "ci/**", ".github/**"]
```

These paths are readable context but cannot be changed by an implementation proposal.

## Critical paths

```json
"critical_paths": ["src/**/security/**", "src/**/contract/**"]
```

A legal change can still be too risky for automatic authority. The `human-gate` scenario demonstrates that distinction.

## Hard budgets

The policy caps changed files and patch bytes.

Budgets create a visible blocked outcome; they do not authorize the controller to drop verification in order to fit.

## Risk boundaries

The goal supplies a risk ceiling and auto-merge ceiling.
Policy independently defines the risk at which human authority is mandatory.

Effective authority is the intersection of those limits.
