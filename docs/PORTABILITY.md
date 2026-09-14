# Portability contract

The reference runtime is intentionally replaceable. The current behavioral contract is `gitops-agent-control-plane/v5`.

Another implementation is compatible only if it preserves these properties:

1. owner goals have explicit authority ceilings;
2. product-authored authority is separate from implementation scope;
3. role reasoning is distinct from controller-observed evidence;
4. writes/budgets/risk ceilings are checked before candidate side effects;
5. new acceptance checks have a meaningful negative control against baseline;
6. verifier definitions are outside the candidate write envelope and their identity is evidence-bound;
7. verifier receipt secrets are not exposed to evaluated code through argv/environment;
8. the trusted receipt producer does not execute/import candidate code in the same process;
9. final verifier receipts are cryptographically authenticated or protected by an equivalent independently controlled result channel;
10. probe/oracle cases are generated at runtime or otherwise resist simple published-fixture lookup overfitting;
11. candidate and post-merge verification evidence is bound to exact revision identities;
12. candidate-process JUnit/test names are not sufficient authorization evidence;
13. failed controller verification blocks merge;
14. critical/high-risk work can require human authority;
15. durable state can recover pending effects without silent duplication;
16. matcher/schema/executor configuration fails closed rather than hanging or silently ignoring constraints;
17. negative scenarios, including receipt forgery and oracle-overfitting attempts, are executable conformance cases.

Run:

```bash
./scripts/agentctl conformance
```

Alternative runtimes may use containers, VMs, remote CI/verifiers or other mechanisms. A production implementation handling untrusted code should use a stronger isolation boundary than the standalone fixture worker. Compatibility is about preserving the trust properties, not copying Python internals.
