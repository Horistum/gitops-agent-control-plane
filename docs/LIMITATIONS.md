# Limitations

## Deterministic roles

The standalone roles are deliberately deterministic. They demonstrate orchestration and trust boundaries, not model quality.

## Local Git

Candidate and merge identities are real Git SHAs, but the merge happens in an isolated local repository. Remote forge permissions and CI producer identity require an integration layer.

## Minimal product

The example is intentionally small so every artifact can be inspected. Production repositories need product-specific authority, test infrastructure, risk classification and recovery procedures.

## JSON Schema execution

Schemas are published as standard Draft 2020-12 documents. The zero-dependency runtime performs its own semantic validation rather than bundling a third-party schema library.

## Single-process demonstration

Crash recovery is simulated by persisting and reloading durable state inside one command. The request identity and state mechanics are real; operating-system process failure injection is outside this compact showcase.
