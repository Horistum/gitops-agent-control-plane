# Adapting the reference

Do not start by connecting a model. Start by defining authority and the verifier trust boundary.

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

Keep structured authority and verification definitions outside the implementation write envelope.

## 2. Define authoritative verification separately from diagnostics

Do not treat test names, counts or JUnit XML produced inside a candidate process as sufficient authorization evidence.

Define protected verification inputs and a verifier-owned result protocol. For new behavior, include a negative control showing that the acceptance check fails against the baseline revision and passes only after the candidate implements the behavior.

For production untrusted/model-generated code, run the verifier behind a container/VM/remote CI boundary whose result channel the candidate cannot write or impersonate.

## 3. Bind verification to exact revisions

Record the exact candidate/merge identity observed by the verifier. A green result without an exact revision identity is incomplete evidence.

## 4. Define path authority

Separate readable context, implementation paths, diagnostic test paths, protected verification inputs, critical paths and controller/CI infrastructure.

## 5. Define risk and human boundaries

Successful verification is not permission to cross a security, contract, credential or migration boundary.

## 6. Preserve durable effect identity

Before a non-idempotent external effect, persist a stable request identity. Recovery should discover whether that exact effect already happened instead of blindly retrying it.

## 7. Add AI last

Replace deterministic role producers with a model only after controller-owned authority, isolated verification and durable execution boundaries work without it.

That keeps AI as a reasoning component instead of accidentally making candidate code or model output the root of trust.
