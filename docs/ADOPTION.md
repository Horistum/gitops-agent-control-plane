# Adapting the reference

Do not start by connecting a model. Start by defining authority, oracle strength and the verifier trust boundary.

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
  verification-probes.json
```

Keep structured authority and verification definitions outside the implementation write envelope. Prefer not to copy verifier definitions into the candidate workspace at all.

## 2. Define properties, not only public examples

Fixed acceptance examples are easy to overfit. Where the domain allows it, define generators plus invariants/properties and create fresh inputs at verification time.

Keep deterministic regression cases too, but do not mistake a small published tuple list for a robust oracle.

## 3. Separate verifier parent from candidate child

Do not execute candidate code inside the process that owns the final evidence secret or oracle decision.

A useful pattern is:

```text
controller
  -> private challenge/key channel
trusted verifier parent
  -> current generated input only
candidate child
  -> raw observation
trusted verifier parent
  -> oracle decision + authenticated receipt
controller
```

Secrets/challenges should not appear in candidate argv, environment or normal stdout.

## 4. Define authoritative verification separately from diagnostics

Do not treat test names, counts or JUnit XML produced inside a candidate process as sufficient authorization evidence.

For new behavior, include a negative control showing that the acceptance property fails against baseline and passes only after candidate implementation.

For production untrusted/model-generated code, run verification behind a container/VM/remote CI boundary whose result channel and verifier internals the candidate cannot access.

## 5. Bind verification to exact revisions

Record the exact candidate/merge identity observed by the verifier plus the verifier-definition identity. A green result without exact revision/verifier identity is incomplete evidence.

## 6. Define path authority

Separate readable context, implementation paths, diagnostic test paths, protected verification inputs, critical paths and controller/CI infrastructure.

## 7. Define risk and human boundaries

Successful verification is not permission to cross a security, contract, credential or migration boundary.

## 8. Preserve durable effect identity

Before a non-idempotent external effect, persist a stable request identity. Recovery should discover whether that exact effect already happened instead of blindly retrying it.

## 9. Add AI last

Replace deterministic role producers with a model only after controller-owned authority, isolated verification and durable execution boundaries work without it.

That keeps AI as a reasoning component instead of accidentally making candidate code or model output the root of trust.
