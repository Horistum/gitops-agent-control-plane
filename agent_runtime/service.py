"""Owner-bound embedding API; scheduling and authenticated tenancy live outside."""
from pathlib import Path

from .actions import action
from .controller import Controller
from .decisions import decision_document
from .io import Busy, locked
from .usage import usage_report


class RunService:
    """Bind a trusted run path once; never accept a caller-selected filesystem path."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def tick(self):
        try:
            return {"outcome": "observed", "state": Controller(self.root).tick()}
        except Busy:
            return {"outcome": "busy", "retryable": True}

    def status(self):
        with locked(self.root):
            return Controller(self.root).summary()

    def decision(self):
        with locked(self.root):
            return decision_document(Controller(self.root).state)

    def usage(self):
        with locked(self.root):
            return usage_report(Controller(self.root).store)

    def approve(self, binding, decision_hash):
        return action(self.root, "approve", binding, decision_hash=decision_hash)
