# Portability contract

The reference runtime is intentionally replaceable.

Another implementation should be considered behaviorally compatible only if it preserves these properties:

1. owner goals have explicit authority ceilings;
2. product-authored authority is separate from implementation scope;
3. role reasoning is distinct from executable evidence;
4. writes are checked before side effects;
5. candidate evidence is bound to an exact revision identity;
6. failed executable verification blocks merge;
7. critical/high-risk work can require human authority;
8. merge/post-merge evidence is bound to exact identities;
9. durable state can recover pending effects without silent duplication;
10. negative scenarios are tested, not merely described.

Run the included conformance matrix:

```bash
./scripts/agentctl conformance
```

An alternative runtime can implement the same scenarios and schemas with different internals.
