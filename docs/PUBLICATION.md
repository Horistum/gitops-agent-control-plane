# Publication readiness

The reference is intentionally free of private runtime names and does not depend on private repositories.

Before making the repository public, still decide:

1. license;
2. contribution policy;
3. security reporting path;
4. release/versioning policy;
5. public support expectations.

A clean-room publication test should clone the repository from a new account/environment and successfully run:

```bash
./scripts/agentctl bootstrap check
./scripts/agentctl validate
./scripts/agentctl demo all
```

No organization-specific access should be required.
