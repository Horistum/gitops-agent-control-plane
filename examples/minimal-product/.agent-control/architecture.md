# Architecture

- `reference_app.service` owns public behavior.
- Name validation and normalization have one source of truth: `normalize_name`.
- Greeting behavior must reuse normalization rather than duplicate it.
- No network, storage, framework, or third-party dependency is required.
- CI and authority files are owner-controlled infrastructure, not implementation scope.
