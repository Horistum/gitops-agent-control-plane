"""One local supervisor; all authoritative transitions still use Controller.tick."""
from datetime import datetime, timezone
from pathlib import Path
import time

from .io import atomic_json, locked
from .service import RunService


def supervise(root, *, poll_seconds=5, max_backoff=60, stop=None, max_ticks=0,
              service=None, wait=None):
    import threading
    root = Path(root).resolve()
    if not 0 < poll_seconds <= max_backoff <= 60 or max_ticks < 0:
        raise ValueError("Supervisor bounds must satisfy 0 < poll <= backoff <= 60")
    stop = stop or threading.Event(); wait = wait or stop.wait
    service = service or RunService(root)
    delay, ticks = poll_seconds, 0
    with locked(root / "supervisor"):
        while not stop.is_set() and (not max_ticks or ticks < max_ticks):
            started = datetime.now(timezone.utc).isoformat()
            atomic_json(root / "health.json", {"state": "ticking", "tick_started_at": started,
                                               "observed": service.status()})
            outcome = service.tick(); ticks += 1
            state = outcome.get("state") or service.status()
            waiting = outcome.get("outcome") == "busy" or state["status"] == "WAITING_EXTERNAL"
            seconds = delay if waiting else (poll_seconds if state.get("paused") or state["status"] != "RUNNING" else 0)
            atomic_json(root / "health.json", {"state": "waiting" if seconds else "running",
                "tick_started_at": started, "tick_finished_at": datetime.now(timezone.utc).isoformat(),
                "next_poll_seconds": seconds, "observed": state})
            if state["status"] in {"COMPLETED", "CANCELLED"}:
                atomic_json(root / "health.json", {"state": "finished", "observed": state})
                return state
            if seconds:
                wait(seconds)
            delay = min(max_backoff, delay * 2) if waiting else poll_seconds
        state = service.status()
        atomic_json(root / "health.json", {"state": "stopped", "observed": state})
        return state
