# Release and versioning policy

Current wire identities are authored in [config/contract-set.json](../config/contract-set.json)
and projected into the [generated contract table](../README.md#contracts).
Library SemVer is independent of those identities.

The current distribution is 1.6.0. Public release tags, when issued, use
`vMAJOR.MINOR.PATCH`; a merged source revision alone does not claim a published
registry release. V7 is breaking because it adds multi-item reconciliation, repair, human resume, release-state transitions, role protocols, and adapter surfaces. A profile change no longer automatically changes the core contract.
