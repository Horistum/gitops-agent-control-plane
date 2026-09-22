"""Bounded discovery observations and retry hints, never task authority."""
import copy


def discovery_document(state):
    discovery = state.get("discovery")
    if not discovery:
        return None
    result = discovery.get("last_result", discovery.get("role_results", {}).get("discovery", {}))
    entries = discovery.get("memory", {}).get("discovery", {}).get("entries", [])
    return copy.deepcopy({
        "head": discovery.get("head"), "turn": discovery.get("turn", 0),
        "context_rounds": discovery.get("context_rounds", 0),
        "eligible_items": state.get("projection", {}).get("eligible_items", []),
        "verdict": result.get("verdict"), "selected_item": result.get("selected_item"),
        "summary": result.get("summary", entries[-1].get("summary") if entries else None),
        "requested_files": discovery.get("requested_files", []),
        "feedback": discovery.get("feedback", [])[-3:],
    })


def can_replan_discovery(state):
    return bool(not state.get("task") and not state.get("pending") and not state.get("owner_intent")
        and state["status"] not in {"COMPLETED", "CANCELLED"}
        and state["model_calls"] < state["policy"]["limits"]["model_calls"])


def remember_discovery(state):
    """Retain one bounded diagnostic and path hints before replan or upgrade.

    Never carry source text, PR facts or memory across a possibly changed base.
    The next discovery rereads all hints from its newly observed Git revision.
    """
    document = discovery_document(state)
    if document is None:
        return
    discovery = state["discovery"]
    sources = discovery.get("memory", {}).get("discovery", {}).get("sources", {})
    state["discovery_retry"] = {
        **{key: document[key] for key in ("head", "verdict", "selected_item", "summary")},
        "reason": state.get("reason"),
        "source_paths": list(dict.fromkeys(discovery.get("requested_files", []) + list(sources)))[:128],
    }


def initial_discovery(state, head, eligible):
    context = list(dict.fromkeys(path for item in state["goal"]["items"] if item["id"] in eligible
                                for path in item["context"]))
    discovery = {"head": head, "base": head, "context": context, "turn": 0}
    previous = state.get("discovery_retry")
    if previous:
        discovery["requested_files"] = list(previous["source_paths"])
        discovery["feedback"] = [{"kind": "previous_discovery",
            **{key: value for key, value in previous.items() if key != "source_paths"}}]
    return discovery
