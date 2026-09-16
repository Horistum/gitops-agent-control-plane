# Operational inputs

These files are templates for the real `agent-control` runtime, not fixture
selectors. Copy both outside the product checkout and fill in the actual product
path, authenticated Codex home, pinned prepared image and GitHub identity/checks.
The illustrative product has `app.py`, `tests/test_base.py` and a protected
`tools/test.py` runner that writes `results/*.xml`. Adapt commands and criteria
to your product; the controller does not invent a test harness from this template.

The goal asks for one new observable behavior. Its `auto_merge_ceiling=none`
requires explicit approval of the resulting candidate. The policy allows only
`app.py` and `README.md` source edits and new independent test files. Existing
tests cannot be overwritten by the tester; tools and GitHub workflow authority
cannot be changed by either role.

Use `agent-control doctor --policy POLICY --goal GOAL` before `start`. Full setup,
local-only operation, recovery and exact approval are in
[the operations guide](../../docs/OPERATIONS.md). Schemas can be printed with
`agent-control schema policy`, `schema goal` or a role such as `schema developer`.

For a credential-free development check, `scripts/check_podman_runtime.py`
creates a disposable real Git product and runs the full lifecycle in actual
containers. Its reasoning peer is explicitly test infrastructure; that check
does not claim to exercise a live model.
