# Portability contract

The reference runtime is intentionally replaceable. Current behavioral contract: `gitops-agent-control-plane/v6`.

A compatible implementation preserves these trust properties:

1. product authority is separate from implementation scope;
2. role reasoning is distinct from controller-observed evidence;
3. write/budget/risk gates precede candidate effects;
4. product verification is expressed outside candidate write scope and evidence-binds its identity;
5. the verifier mechanism is product-neutral, supporting reusable generators/invariants rather than hardcoded application-specific oracle functions;
6. new acceptance behavior has a **case-level** negative control where every generated acceptance case is rejected by baseline;
7. evaluated code cannot mint the final trusted verifier receipt merely by writing process output;
8. negative scenarios prove the attack path actually executed;
9. candidate/post-merge verification binds to exact revisions;
10. diagnostic JUnit/test names are not authorization evidence;
11. critical work may require human authority;
12. durable pending effects recover without silent duplication;
13. matcher/schema/executor configuration fails closed;
14. core authority/effect/human-gate artifacts have machine validation.

The standalone implementation uses a small generic DSL with positional args, kwargs, generators and declarative expressions. Alternative runtimes may implement equivalent semantics differently.

Production systems handling untrusted code should use a container, VM or remote verifier whose process/filesystem and result channel are outside candidate control. Compatibility concerns behavioral trust properties, not copying Python internals.
