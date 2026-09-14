# Limitations

The reference is deliberately executable, but it is not a production autonomous engineering runtime.

## No security sandbox

The local executor is suitable only for trusted deterministic fixtures. Timeout/resource limits are not filesystem or network isolation. Untrusted model-generated code must not be connected to it.

## No evidence authenticity anchor

The event chain provides internal consistency only. It does not defeat a party able to rewrite the complete evidence directory.

## No remote forge/CI proof

Local Git commits and tests demonstrate exact-identity mechanics. A production adapter must separately establish remote Git, trusted CI producer identity, credentials and remote effect semantics.

## Natural-language policy is not magically executable

Structured paths, risk rules, acceptance-test identities and quality-gate fields are enforced. Free-form explanatory fields remain context, not hard gates, unless translated into structured policy.

## Reference fixtures are deterministic

They demonstrate controller behavior, not model capability or model independence. The important separation is that controller gates do not accept role assertions as proof.
