# Agent and model execution model

This document describes both meanings of “model” that matter here: the multi-role engineering model
and the concrete LLM selection.

## 1. Five trusted roles

FlowAI-Control 0.3.0 ships five reviewed role instruction files inside the controller runtime:

| Role | Responsibility |
|---|---|
| `chief-architect` | discovery-level and highest-risk goal/plan acceptance |
| `task-architect` | task architecture, invariants, working set and architecture acceptance |
| `developer` | bounded implementation proposal |
| `tester` | independent test design and independent executable test proposal |
| `reviewer` | independent review and challenge review |

The tenant repository does not redefine these role prompts. Their bytes are included in the policy
fingerprint through the runtime, so silently swapping role instructions changes execution identity.

## 2. Controller phases and role mapping

The controller has more phases than roles because one trusted role may serve multiple independent
gates:

| Phase | Role / executor | Main output |
|---|---|---|
| `discovery` | chief architect | one authorized task candidate |
| `baseline` | controller test runner | exact baseline receipt |
| `architect` | task architect | working set, invariants, plan, risk |
| `test_design` | tester | independent scenarios |
| `chief_plan` | chief architect | high-risk plan gate |
| `developer` | developer | edits + acceptance evidence |
| `verify` | controller test runner | candidate test receipt |
| `tester` | tester | independent test edits/evidence |
| `independent_verify` | controller test runner | executable independent receipt |
| `reviewer` | reviewer | findings + acceptance evidence |
| `challenge_review` | reviewer | adversarial second review when policy triggers it |
| `architect_accept` | task architect | architecture/acceptance verdict |
| `chief_accept` | chief architect | highest-risk goal acceptance |
| `publish/ci/merge/postmerge` | controller + GitHub | deterministic lifecycle evidence |

Adaptive routing may skip phases that are not required for the current risk, but it cannot skip a
phase whose stronger risk classification makes it mandatory.

## 3. Strict structured output

A model does not return prose for the controller to “interpret generously.” Every active phase has a
strict JSON schema.

All model phases carry:

- `verdict`;
- `summary`;
- `risk`;
- `requested_files`;
- `requested_searches`;
- `requested_facts`;
- typed findings.

Phase-specific payloads add task selection, plan, edits, test scenarios or acceptance evidence.
Missing required fields, unexpected fields, malformed enums or oversized structures are protocol
failures.

This is intentional. An autonomous controller whose protocol means “whatever the model probably
intended” is just a very expensive ambiguity generator.

## 4. Model sessions are data-only

The Codex session is deliberately weaker than the controller:

- read-only sandbox;
- no shell tool;
- no unified exec;
- no multi-agent delegation;
- no web search;
- no GitHub token inherited;
- no product Git checkout as a writable model workspace;
- no permission to claim that it executed tests.

The controller supplies bounded repository context and can satisfy explicit
`requested_files` / `requested_searches` / `requested_facts` requests within policy budgets.

Repository content and prior reports are framed as untrusted data, not instructions.

## 5. Model selection

`policy.models` maps trusted role name to a Codex model name. A `default` key is the fallback:

```json
{
  "models": {
    "default": "MODEL_NAME",
    "chief-architect": "OPTIONAL_STRONGER_MODEL"
  }
}
```

An empty object delegates selection to the installed Codex CLI default.

Do not encode behavioral authority in model names. Safety comes from controller policy, role
contracts, structured output and deterministic gates. A stronger model may improve proposal quality,
but it does not gain extra privileges.

## 6. Context is phase-scoped

Two policy structures bound context:

- `phase_context_paths`: which already-approved authority files each phase may see;
- `phase_context_bytes`: maximum phase budget.

Every phase path must also exist in top-level `context_paths`. This prevents a role-specific context
entry from secretly expanding authority.

The reference keeps discovery broad enough to understand the roadmap and keeps later phases focused
on architecture and quality contracts.

## 7. Evidence is not opinion

There are two fundamentally different evidence classes:

**Model evidence** says a role inspected a candidate and produced a typed verdict tied to exact
candidate identity.

**Executable evidence** says the controller actually ran owner-approved commands in the pinned test
image or observed trusted GitHub checks on an exact SHA.

FlowAI-Control requires both where appropriate. A reviewer writing “tests pass” cannot replace a
test receipt.

## 8. Risk graph

Use these as operational intuition, not as a replacement for controller code:

- **LOW**: smallest graph consistent with independent implementation verification.
- **MEDIUM**: includes independent test design and architecture acceptance; challenge review can be
  required by policy.
- **HIGH or critical path**: conservative full graph and explicit owner decision before dangerous
  progress/merge.

Risk can escalate after architecture or implementation facts become clearer. Escalation invalidates
candidate-level evidence that is no longer strong enough.

## 9. Billing boundary

This compatible 0.3.0 policy accepts only:

```json
{
  "provider": "chatgpt",
  "credit_mode": "included_then_purchased",
  "api_fallback": false
}
```

The runtime does not silently fall back to `OPENAI_API_KEY`. Provider quota exhaustion becomes a
bounded wait, not permission to change billing authority.
