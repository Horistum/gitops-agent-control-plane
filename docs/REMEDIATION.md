# Architectural remediation and evidence scope

The operational runtime uses one shared workflow aggregate and exact-revision
release gate. Its public integration tests exercise actual Git/process effects,
bounded recovery, independent verification, typed acceptance, and owner controls.
Historical consumer compatibility or deployment records are not current public
release evidence. Generate exact-input reports as described in
[validation](../validation/README.md).

## Earlier review remediation

### Historical operational release — 1.4.0

The first remediation, core 1.3.0, repaired library defects and clarified fixture
scope. It did **not** deliver the working model-driven development controller
requested in the review. Version 1.4.0 adds that executable runtime while retaining
the earlier correctness fixes and reproducible fixture demonstrations.

## Findings, implementation and evidence

| Review finding | Delivered correction | Executable evidence |
|---|---|---|
| Reasoning roles were hard-coded source fixtures | Codex structured output or an external JSON provider produces every operational role response; no operational fixture selector | Separate-process provider lifecycle; Codex protocol negatives; actual pinned Codex CLI capability check in CI |
| Real runtime adapters absent | Real Git snapshots/commits, rootless Podman execution, authenticated GitHub publication/check/governance/merge, installed owner CLI | Real Git/process lifecycle; actual Podman CI; HTTP contract peer with real remote Git and lost-write recovery |
| Complete graph and context/recovery APIs unintegrated | Full shared graph, revision-scoped context, dependency reconciliation, recovery, retirement and upgrades used by operational controller | Two dependent items traverse the complete graph and retain earlier tests; context, recovery and upgrade regressions |
| Independence and acceptance only isolated vectors | New tests fail on original code and pass on candidate; assertions freeze across repairs/replans; typed CI/delivery obligations defer until observed | Tautology rejection, harness-error hold, real failed implementation repair, future-evidence rejection, retained regressions |
| Authority and interrupted effects | Exact approval; protected paths; monotonic risk; lifetime call budget; durable receipts; explicit uncertain-call retry; reconcile merged effects before cancellation | Base movement, protected edit, receipt crash, uncertain call, bounded replan/upgrade, lost PR/merge/close and concurrent close/merge cases |
| Repeated contract identities | One authored fixture manifest and generated projections; operational schemas generated from runtime contracts | Both generators have mandatory drift checks |
| Inconsistent public API | Complete package-root and explicit submodule exports; pure core remains independently usable | Shared conformance, installed imports, consumer compatibility gate |
| Duplicate gates and large legacy engine | Shared path decision; extracted attempt, human, lifecycle and evidence responsibilities; old helpers use enforced engine | Original security and entrypoint regressions |
| Fragmented or overstated documentation | Five primary guides distinguish operational execution, fixtures, pure core and deployment evidence | README/docs consistency checks and this remediation map |
| JSON Schema semantic differences | Correct boolean/number equality, integer-valued numbers, uniqueness, regex semantics and full-string identities; unknown keywords fail closed | Required comparison against Draft202012Validator for supported cases and all published schemas |

Operational modules separate contracts, reasoning, Git, GitHub, verification,
durable store, roles, lifecycle and owner actions. The core retains no process,
network, credential or Git effects. A consumer can reuse its decisions without
deploying the operational CLI.

## Validation and remaining evidence boundaries

`./scripts/agentctl validate` runs the complete unit/integration suite and all discovered
deterministic conformance scenarios. Operational tests execute real edits, test
failures, repairs, commits and merges. Reasoning and HTTP peers are controlled
test infrastructure, explicitly located under `tests/`.

CI additionally runs the lifecycle in actual rootless Podman, runs the two-item
lifecycle from an installed wheel outside the checkout, and checks the actual
pinned Codex CLI contract. These jobs must pass before merging. They do not spend
a model subscription or publish a test PR in someone else's product repository.

The generic consumer gate records a clean consumer revision and current core
hashes in an operator-selected report outside the source tree. Passing it does
not publish a consumer's adoption changes or activate a live installation.

A live authenticated Codex turn and delivery to an operator's protected GitHub
product remain installation evidence, not results of test doubles. The
[operations guide](OPERATIONS.md) provides the runnable path and prerequisites.
No model quality, universal correctness or deployment success is inferred from
a passing test suite.

The local property-probe `raw-outcome-forgery` KNOWN-LIMIT remains reproduced.
Rootless containers protect the controller boundary; candidate-written JUnit can
still lie about candidate behavior. Parent-observed process assertions, protected
verifier code, counterfactual tests and review reduce this risk within the finite
declared scope. See [verification](VERIFICATION.md).

```bash
./scripts/agentctl validate
python3 -m pip install -r requirements-test.txt
PYTHONPATH=. python3 tests/test_schema_interoperability.py --require-reference -v
python3 scripts/check_podman_runtime.py --image PINNED_IMAGE
python3 scripts/check_consumer.py --consumer /absolute/consumer-checkout \
  --expected-commit FULL_CONSUMER_SHA --output /absolute/private-audit/consumer-compatibility.json
```
