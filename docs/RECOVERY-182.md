# 1.8.2: diagnose and recover discovery holds

`BLOCKED_POLICY`, `phase=reconcile`, `item=null` and the message
`Discovery did not select eligible authorized work` mean that the provider returned
a valid role response but did not select an authorized eligible item with
`verdict=ready`. This message is not a GitHub authentication error or proof that
the model-call budget is exhausted. The precise cause is in the response.

Repeated RUNNING/reconcile observations before the hold can be context requests
or protocol repairs. They do not indicate completed implementation work.
Replanning is an explicit new attempt and can incur more model calls.

## Inspect an existing run without calling the provider

```bash
agent-control status --state ./run-state-2
agent-control decision --state ./run-state-2
agent-control usage --state ./run-state-2
```

In 1.8.2, `discovery` reports the exact verdict, selected ID, eligible IDs, summary,
context round and requested files. `decision.reviews.discovery` contains final
findings; `decision.feedback` contains context/protocol errors. Reads also work
before upgrading the runtime fingerprint. Older states have no recorded selected
ID in their role summary; this is reported as null rather than guessed.
After a replan or upgrade, `decision.previous_discovery` retains the diagnosis
until a new selection succeeds.

Before installing the correction, the 1.8.1 saved diagnosis can be inspected with
the standard library alone:

```bash
python3 - <<'PY'
import json
from pathlib import Path
state = json.loads(Path('run-state-2/state.json').read_text())
discovery = state.get('discovery') or {}
print(json.dumps({
    'goal': state['goal'],
    'eligible_items': state.get('projection', {}).get('eligible_items'),
    'last_result': discovery.get('role_results', {}).get('discovery'),
    'feedback': discovery.get('feedback', []),
    'context': discovery.get('memory', {}).get('discovery'),
}, ensure_ascii=False, indent=2))
PY
```

Inspect the goal and source paths as well as the summary. The example goal that
requests `Return 2 from value()` in `app.py` is for the fixture product; it does
not authorize arbitrary work in another repository. If the intended goal or
policy needs changing, author corrected inputs and start a separate run.
Editing an existing `state.json` to change authority invalidates its hash.

## What changed

- Discovery starts with the contexts of dependency-ready authorized items,
  retrieved from the actual discovery head. The file and byte limits still apply.
  Overflow is exposed as omitted paths, and subsequent explicit file requests
  take priority over initial hints.
- The prompt distinguishes selecting work for planning from proving final
  acceptance. Missing future tests/CI/merge evidence does not by itself prevent
  selecting authorized implementation work. Concrete conflicts still block.
- Refusals expose the verdict, selected ID, eligible IDs and model summary.
  Unselected work is never silently replaced by the first eligible item.
- A discovery replan preserves the last diagnosis and bounded source-path hints.
  All source contents are reread at the newly observed head; old facts and model
  memory are not carried as current evidence. The stale top-level hold reason is
  cleared when replan returns RUNNING.
- The owner decision offers discovery replan when it is available. Exhausted
  budgets and pending effects prevent this action. `resume` alone never retries
  a held discovery and never repeats a recorded model call.

## Upgrade a blocked run with no task or pending effect

Use the same absolute state path throughout, especially if changing directories
to update the controller checkout. Pause with the old runtime before installing
the reviewed 1.8.2 source, following the installation method used for this runtime.

```bash
agent-control pause --state /absolute/path/run-state-2
# Install the reviewed 1.8.2 controller source in the active environment.
agent-control upgrade --state /absolute/path/run-state-2
agent-control decision --state /absolute/path/run-state-2
agent-control replan --state /absolute/path/run-state-2 --reason 'Retry with corrected discovery context and prompt'
agent-control continue --state /absolute/path/run-state-2
agent-control resume --state /absolute/path/run-state-2
```

`upgrade` preserves discovery hints but does not release a BLOCKED_POLICY hold;
`replan` does that explicitly. `continue` releases the pause. The call budget is
not reset. A missing/indeterminate pending effect must be reconciled separately
before upgrade; see [receipt recovery](RECOVERY-180.md).

Regression tests use disposable Git repositories and controlled providers. They
cover initial context, bounded retrieval, actionable refusal diagnostics,
unauthorized IDs, unchanged held resumes, fresh source reads after replan, budget
exhaustion and legacy-state upgrades. They make no claim about a particular live
model's refusal without inspecting that run's saved response.
