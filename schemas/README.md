# Published schemas

Contract identities are generated from [config/contract-set.json](../config/contract-set.json).
See the [contract table](../README.md#contracts) and [schema interoperability](../docs/VERIFICATION.md#json-schema-compatibility).

The schemas use a supported subset of Draft 2020-12. The runtime rejects unsupported
keywords, including nested ones. CI validates the schemas with a standard validator
and compares supported instance semantics. Runtime semantic authority checks remain
additional constraints beyond structural JSON Schema validation.
