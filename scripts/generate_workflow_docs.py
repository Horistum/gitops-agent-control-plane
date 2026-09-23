#!/usr/bin/env python3
"""Render the normal phase graph from the shared reducer; --check detects drift."""
import argparse
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent_runtime.explain import workflow_path


def diagram():
    edges, sources, order = defaultdict(set), defaultdict(set), []
    for risk in ("low", "medium", "high"):
        for challenge in (False, True):
            phases = []
            for phase in workflow_path(risk=risk, challenge=challenge):
                phases.append(phase)
                if phase in {"developer", "tester"}:
                    phases.append("apply_" + phase)
            for phase in phases:
                if phase not in order:
                    order.append(phase)
            for source, target in zip(phases, phases[1:]):
                edges[source, target].add((risk, challenge))
                sources[source].add((risk, challenge))
    lines = ["flowchart TD"]
    for phase in order:
        lines.append(f'    {phase}["{phase}"]')
    for (source, target), variants in edges.items():
        label = ""
        if variants != sources[source]:
            levels = {risk for risk, _ in variants}
            challenges = {challenge for _, challenge in variants}
            if variants == {v for v in sources[source] if v[0] in levels}:
                label = "/".join(r for r in ("low", "medium", "high") if r in levels)
            elif variants == {v for v in sources[source] if v[1] in challenges}:
                label = "challenge" if True in challenges else "no challenge"
            else:
                label = "/".join(r for r in ("low", "medium", "high") if r in levels)
                label += " + " + ("challenge" if True in challenges else "no challenge")
        arrow = f' -->|"{label}"| ' if label else " --> "
        lines.append("    " + source + arrow + target)
    return "\n".join(lines)


HEADER = """# Workflow map

The diagram below is generated from the actual shared
`workflow_transition(..., {"kind": "advance"})` reducer for all three risk
levels, with and without challenge review. It shows the **normal route of one
selected item**, not elapsed progress. Discovery (`reconcile`) selects an
eligible authorized item before `baseline`; after `done`, the controller checks
the goal and either selects another item or completes the run.

The operational adapter's `apply_developer` and `apply_tester` boundaries are
shown explicitly. Proposed edits are validated and applied by the controller.

```mermaid
"""

FOOTER = """
```

## Which route applies?

| Condition | Effective graph |
|---|---|
| Adaptive enabled, no critical change | Item's current low / medium / high risk |
| Critical change detected | High, even if the reported risk is lower |
| Adaptive disabled | High |
| Challenge enabled | Adds challenge_review and architect_accept, including at low risk |

Risk can increase during an attempt. Missing test_design / chief_plan gates run
before resuming developer or verify via the recorded risk_gate_return. A higher
graph invalidates the candidate, reviews, CI and approval that no longer apply.

## Repairs, holds and effect boundaries

The graph describes successful advancement. These events can interrupt it:

| Event | Result |
|---|---|
| Product failure in verify, independent_verify or CI | Returns to developer within the bounded repair rules |
| Independent baseline fails its expected negative control | Returns to tester; with frozen tests, awaits the owner |
| Baseline/postmerge failure or an unavailable verification outcome | await_human; evidence determines whether retry is allowed |
| Review asks for repair | Returns to architect, test_design, developer or tester, with evidence invalidated |
| Base changes before merge | baseline is repeated; stale evidence/approval is invalidated |
| Owner approval required or policy/protocol violation | Held state; explain shows the original phase and the allowed recovery |
| External dependency unavailable | WAITING_EXTERNAL, normally retaining the execution phase |
| Uncertain model effect | Held for its original receipt or an explicit potentially charged retry |
| Pause | Orthogonal stop flag; it does not itself clear a hold |

The actual controller may also repair protocol/context responses within its
configured budget before holding. No diagram edge authorizes a model dispatch,
edit, merge or retry: the core evidence checks and durable effect receipts still
govern those operations. Independent baseline verification may intentionally
contain failing tests: it must establish the expected negative control.

## Keep this map current

`python3 scripts/generate_workflow_docs.py` regenerates this file.
`./scripts/agentctl validate` checks it against the reducer. CLI/UI routes are
derived from the same reducer; the UI separately shows actual recorded
transitions so a repair loop is visible rather than hidden by a progress bar.

Sources: [portable workflow](../control_plane_core/workflow.py),
[operational roles](../agent_runtime/roles.py),
[verification and release](../agent_runtime/lifecycle.py).
See [operator guide](OPERATOR-EXPERIENCE.md) for recovery commands and state layout.
"""


def render():
    return HEADER + diagram() + "\n" + FOOTER


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "docs" / "WORKFLOW.md"
    expected = render()
    if args.check:
        if not path.exists() or path.read_text() != expected:
            raise SystemExit("Workflow documentation drift; run python3 scripts/generate_workflow_docs.py")
    else:
        path.write_text(expected)


if __name__ == "__main__":
    main()
