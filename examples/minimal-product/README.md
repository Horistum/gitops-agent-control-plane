# Minimal reference product

This product is intentionally tiny so every autonomous-delivery artifact remains inspectable.

The starting implementation provides only:

```python
normalize_name("  Ada   Lovelace ") == "Ada Lovelace"
```

and three green regression tests.

`EXAMPLE-001` asks the reference runtime to add:

```python
greet("  Ada   Lovelace ") == "Hello, Ada Lovelace!"
```

The correct candidate must reuse `normalize_name`, reject blank input, add executable tests, and preserve product authority.

## Product-authored authority

`.agent-control/` contains:

- `authority.md`
- `architecture.md`
- `roadmap.json`
- `release-state.json`
- `forbidden.json`
- `quality-gates.json`

Those files are readable context but not implementation scope.

## Baseline

```bash
python3 ci/run_tests.py
```

Three tests pass and JUnit is written under:

```text
build/test-results/reference/TEST-reference.xml
```

The standalone scenarios copy this product to an isolated workspace. The source example is never modified by a demo run.
