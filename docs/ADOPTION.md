# Adapting the reference

Do not start by connecting a model. Start by defining authority.

## 1. Replace the example product authority

Create your equivalent of:

```text
.agent-control/
  authority.md
  architecture.md
  roadmap.json
  release-state.json
  forbidden.json
  quality-gates.json
```

Keep these files outside the normal implementation write envelope.

## 2. Define deterministic verification

A production system needs executable commands whose outputs can be tied to an exact candidate revision.

Record test identities, not only exit code.

## 3. Define path authority

Separate:

- readable authority/context;
- normal implementation paths;
- critical paths;
- controller/CI infrastructure.

## 4. Define risk and human boundaries

A successful test is not permission to cross a security, contract, credential or migration boundary.

## 5. Preserve evidence identities

Your external Git/CI adapter should preserve the same relationships shown locally:

```text
base revision
  -> candidate revision
      -> candidate verification
          -> merge revision
              -> post-merge verification
```

## 6. Add AI last

Replace deterministic role producers with a model only after controller-owned policy, execution and evidence boundaries work without it.

That keeps AI as a reasoning component instead of accidentally making it the root of trust.
