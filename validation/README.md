# Validation records

`consumer-compatibility.json` records one source compatibility run of core 1.3.0
against the exact named FlowAi-control commit. Its `core_files` hashes identify
what was tested; this is historical evidence, not a claim about future consumer
commits or a live deployment. The temporary core commit itself is not published.

Reproduce with `scripts/check_consumer.py` and an exact clean consumer checkout.
The gate runs real local tests in an isolated temporary copy, updates the temporary
source lock and checks that the core bytes remain unchanged. It requires no live
Codex, hosted GitHub write, Podman build or deployment. Provider responses may be
test doubles in the consumer's suite, as documented by that consumer.
