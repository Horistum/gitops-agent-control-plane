# Architecture constitution

1. `src/reference_app/` contains product behavior.
2. `tests/` contains executable behavioral verification.
3. `ci/run_tests.py` and `.github/workflows/` are owner-controlled infrastructure, not product scope.
4. Public functions must be deterministic and side-effect free in this reference product.
5. Invalid caller input must fail explicitly. Do not silently coerce blank names.
6. Keep one implementation of name normalization. Do not duplicate normalization logic in `greet`.
7. No network, filesystem, environment or time dependency may be added to `reference_app.service`.
