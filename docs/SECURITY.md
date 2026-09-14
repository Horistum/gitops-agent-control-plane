# Security model

The main threat is an autonomous system that can both make a change and weaken the rules used to approve that change.

The reference therefore separates authority from implementation.

## Demonstrated controls

- product authority is outside implementation write scope;
- proposals are checked before mutation;
- executable tests run outside reasoning roles;
- exact Git candidate and merge identities are recorded;
- critical paths trigger a human gate;
- event history is hash-linked;
- pending external effects carry durable request identities;
- demo evidence is append-style run output, not product authority.

## Deliberately excluded

The standalone showcase has no credentials, network integration, external model or remote merge authority, so it does not pretend to prove controls for those systems.

A production adapter must add its own credential isolation, external CI identity and remote-effect semantics without weakening the portable guarantees.
