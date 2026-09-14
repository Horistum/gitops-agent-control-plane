# Architecture

- `reference_app.service` is the only public implementation module.
- Name validation/normalization has one source of truth: `normalize_name`.
- New greeting behavior must reuse normalization rather than duplicate it.
- No network, storage, framework or third-party dependency is needed for this example.
- CI and authority files are owner-controlled infrastructure, not implementation scope.
