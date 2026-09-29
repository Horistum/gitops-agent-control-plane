"""Purpose-bound owner authority normalized for the portable core."""
from control_plane_core import candidate_authorization, path_allowed, work_authorization


def _policy(state):
    return {"policy_hash": state["policy_hash"], "runtime_hash": state["runtime_hash"],
            "run_id": state["run_id"]}


def work_critical_paths(state):
    task = state["task"]
    working = task.get("working_set", [])
    planned = [path for path in working if path_allowed(path, state["policy"]["critical_paths"])]
    return sorted(set(planned) | set(task.get("candidate_critical_paths", [])))


def work_binding(state):
    task = state["task"]
    return work_authorization({**task, "plan": task.get("plan", []), "working_files": task.get("working_set", []),
        "scenarios": task.get("test_design", [])}, policy=_policy(state), goal=state["goal"],
        critical_paths=work_critical_paths(state))


def approval_binding(state):
    return candidate_authorization(state["task"], policy=_policy(state), goal=state["goal"],
        critical_paths=state["task"].get("candidate_critical_paths", []))


def work_gate(engine):
    """Planning is reviewable before authorization; every later effect rechecks it."""
    task = engine.task
    if task["risk"] != "high":
        return True
    binding = work_binding(engine.state)
    if task.get("work_approval") == binding:
        return True
    task.update(work_approval_required=binding, approval_purpose="work-plan")
    engine.hold("Owner authorization required for this work plan and scope", kind="NEEDS_DECISION", approvable=True)
    return False
