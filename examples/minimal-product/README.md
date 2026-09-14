# Minimal autonomous-delivery product

This repository is deliberately boring. That is useful.

The baseline already passes three tests for `normalize_name()`. Roadmap item `EXAMPLE-001` asks the control plane to add one small public function:

```python
greet("  Ada   Lovelace ") == "Hello, Ada Lovelace!"
```

The new implementation must reuse existing normalization behavior, reject blank names, add executable tests and leave CI/authority files untouched.

## Baseline

```bash
python3 ci/run_tests.py
```

The runner writes JUnit to:

```text
build/test-results/reference/TEST-reference.xml
```

This makes test identities observable rather than treating exit code zero as sufficient proof.

## Authority

`.agent-control/` contains product-authored roadmap, architecture, release state, forbidden directions and quality gates. These files are controller input but are outside normal product write scope.

## Why this example is small

A first autonomous run should make every artifact inspectable: goal, plan, diff, tests, review, candidate SHA, CI, merge SHA and post-merge evidence. Once that path is trustworthy, adapt the same model to a real repository rather than proving the concept on an already complicated system.
