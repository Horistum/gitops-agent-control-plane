# Portability contract

The reference runtime is intentionally replaceable. The current behavioral contract is `gitops-agent-control-plane/v4`.

Another implementation is compatible only if it preserves these properties:

1. owner goals have explicit authority ceilings;
2. product-authored authority is separate from implementation scope;
3. role reasoning is distinct from controller-observed evidence;
4. writes/budgets/risk ceilings are checked before candidate side effects;
5. new acceptance checks have a meaningful negative control against the baseline;
6. authoritative verification definitions are outside the candidate write envelope;
7. candidate verification requires an execution completion signal controlled by the verifier, not merely candidate process exit/JUnit output;
8. candidate and post-merge verification evidence is bound to exact revision identities;
9. candidate-process JUnit/test names are not sufficient authorization evidence;
10. failed controller verification blocks merge;
11. critical/high-risk work can require human authority;
12. durable state can recover pending effects without silent duplication;
13. matcher/schema/executor configuration fails closed rather than hanging or silently ignoring constraints;
14. negative scenarios, including evidence-forgery attempts, are executable conformance cases.

Run:

```bash
./scripts/agentctl conformance
```

Alternative runtimes may use containers, VMs, remote CI/verifiers or other mechanisms. In fact, a production implementation handling untrusted code should use a stronger isolation boundary than the standalone fixture worker. Compatibility is about preserving the trust properties, not copying Python internals.
