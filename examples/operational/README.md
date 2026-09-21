# Operational inputs

These files are templates for the real `agent-control` runtime, not fixture
selectors. Copy both outside the product checkout and fill in the actual product
path, trusted command provider, model credential reference, pinned prepared image
and GitHub identity/checks. `policy.example.json` is the primary provider-neutral
profile; `policy.codex.example.json` retains the optional authenticated Codex profile.
An optional concrete API adapter is installed as `agent-reasoning-openai`; use
`policy.openai.example.json` and configure an available model and explicit API key
reference. This is an owner-selected API billing path, never a fallback from Codex.
The primary generic template still requires your own trusted adapter and its
non-billing `check_argv` handshake. Implement the [documented command protocol](../../docs/MIDDLEWARE.md).
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
