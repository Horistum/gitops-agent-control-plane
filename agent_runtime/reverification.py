"""Owner-only re-observation of exact completed verification inputs."""
from control_plane_core import CoreError, fingerprint
from control_plane_core.reverification import authority, binding, failed_observation, resume
from .io import Closed


def current_authority(state):
    return authority(state.get("task") or {}, policy=state["policy_hash"],
                     goal=fingerprint(state["goal"]), runtime=state["runtime_hash"])


def recovery_binding(state):
    if (not (state.get("task") or {}).get("verification_recovery")
            or state.get("pending") or state.get("owner_intent")
            or (state.get("technical_recovery") or {}).get("exhausted")):
        return None
    return binding(state.get("task") or {}, current_authority(state))


def record_failure(engine, phase, receipt):
    engine.task["verification_recovery"] = failed_observation(current_authority(engine.state), phase, receipt)


def reverify(engine, expected):
    if not expected or recovery_binding(engine.state) != expected:
        raise Closed("Reverification binding is stale, unavailable or exhausted")
    try:
        result = resume(engine.task, current_authority(engine.state), expected)
    except CoreError as exc:
        raise Closed(str(exc)) from exc
    engine.task.setdefault("verification_recovery_history", []).append(result["record"])
    engine.task.pop("verification_recovery")
    engine.task.update(phase=result["phase"], reverifications=result["reverifications"], retryable=False)
    engine.task.pop("hold_kind", None)
    engine.state.update(status="RUNNING")
    # Only verification receipts get a new key. Model identities and budgets stay intact.
