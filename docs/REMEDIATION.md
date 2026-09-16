# Architectural review remediation — core 1.3.0

The project delivers a portable authority/effect/evidence decision library and a
trusted deterministic executable reference. It is useful as reusable controller
logic and an adapter contract, with a deliberately bounded validation claim.
It does not provide a live AI development service or a new deployment daemon.

## Findings and implemented corrections

| Review finding | Correction | Executable evidence |
|---|---|---|
| Fixture behavior presented as AI autonomy | README opens with fixture scope; plans/checklist/repair and live-provider boundary are explicit | Existing scenarios retain their real meaning; no AI-generation claim |
| Repeated contract IDs | `config/contract-set.json` is authored once; generator updates policy, schemas, core constant and README | `test_contract_generation.py`; drift gate in `agentctl validate` |
| Core graph partly unexercised, independent baseline unreachable | `tester` enters `independent_baseline`; all graph levels and challenge paths covered; public local adapter integration and repeatable consumer compatibility gate | `execution_conformance.py`, `test_adapter_integration.py`, `scripts/check_consumer.py` |
| Inconsistent public API | Complete package-root exports plus explicit supported submodule exports; old submodule imports remain valid | `control_plane_core.conformance`, standalone package import test |
| Duplicate path gates | BaseEngine has an abstract gate; the composed engine calls the shared core with active role authority | Role-authority tests; historical helper regression |
| Fragmented documentation | Five primary guides with retained link aliases | README navigation; existing documentation checks |
| Minimal schema semantics diverged | Strict JSON boolean/number equality, integer-valued numbers, uniqueness, standard regex search, unknown-keyword preflight | Supported-case tests plus required CI comparison against Draft202012Validator |
| Identity patterns relied on nonstandard implicit anchoring | Published patterns explicitly constrain the full string under standard and local validators | Hash suffix/prefix/newline regressions |
| Large engine and version-layer ambiguity | Attempt, human, effect and evidence responsibilities extracted; orchestration implementation reduced from 1,241 to about 330 lines | Full reference suite and crash/recovery conformance |
| Older helpers could run an engine without current role/identity gates | Old run/resume/CLI helpers forward to the public composed engine; no permissive base path fallback | `test_runtime_entrypoints.py` runs denied role authority through all helper entry points |

Additional safety corrections reject arbitrary resume points to merge/completion,
invalid context retention limits, missing acceptance specification identity, and
candidate errors outside bound tests. Mixed assertion/harness failures route to an
ambiguous failure instead of confidently attributing the problem to product code.

The schema criticism required precision: using a supported subset does not make
schemas invalid for standard JSON Schema validators. The actual semantic
mismatches were repaired; unsupported vocabularies still fail closed locally.

## Consumer evidence and migration

The original FlowAi-control suite passed 406 tests. With this core snapshot and an
accurate temporary source lock, 413 tests passed on Python 3.12. The consumer
revision, tree and exact core file hashes are preserved in
[consumer-compatibility.json](../validation/consumer-compatibility.json).
The extra tests come from the expanded shared conformance modules.

The observed consumer already explicitly chooses its independent-baseline stage
under its strict verification profile. The shared graph correction therefore
preserves this consumer's tested behavior. Source compatibility is confirmed for
the recorded revision; GitHub API responses, Codex turns and production isolation
still require the consumer's live-host gates.

This change updates this reference repository. It does not silently change the
consumer's source lock, deployed runtime or activation. Adoption remains a
reviewed source synchronization, consumer CI and host validation operation.

## Validation commands

```bash
./scripts/agentctl validate
python3 -m pip install -r requirements-test.txt
PYTHONPATH=. python3 tests/test_schema_interoperability.py --require-reference -v
python3 scripts/check_consumer.py --consumer ../FlowAi-control \
  --expected-commit FULL_CONSUMER_SHA --output consumer-compatibility.json
```

The local fixture executor's `raw-outcome-forgery` KNOWN-LIMIT remains reproduced.
A green scenario suite means the limitation is correctly characterized, not that
hostile arbitrary code has become isolated. No theorem-proving or live-model
validation claim is made.
