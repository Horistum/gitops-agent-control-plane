# Release and versioning policy

Current wire identities are authored in [config/contract-set.json](../config/contract-set.json)
and projected into the [generated contract table](../README.md#contracts).
Library SemVer is independent of those identities.

Public tags use `vMAJOR.MINOR.PATCH`; intended first public release remains `v0.1.0` after clean-room publication gates. V7 is breaking because it adds multi-item reconciliation, repair, human resume, release-state transitions, role protocols, and adapter surfaces. A profile change no longer automatically changes the core contract.

