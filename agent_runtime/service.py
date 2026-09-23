"""Owner-bound embedding API; scheduling and authenticated tenancy live outside."""
from pathlib import Path

from .actions import action
from .controller import Controller
from .decisions import decision_document
from .io import Busy, Closed, locked
from .store import Store
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
        from .observations import status_document
        return status_document(Store(self.root).state, self.root)

    def decision(self):
        return decision_document(Store(self.root).state)

    def usage(self):
        return usage_report(Store(self.root))

    def diagnostics(self, limit=20):
        from .diagnostics import recent_events
        return recent_events(self.root, limit)

    def explain(self, limit=10):
        from .explain import explanation_document
        return explanation_document(Store(self.root), limit)

    def approve(self, binding, decision_hash):
        return action(self.root, "approve", binding, decision_hash=decision_hash)

    def act(self, name, decision_hash, *, binding=None, reason=""):
        return action(self.root, name, binding, decision_hash=decision_hash, reason=reason)

    def diff(self, decision_hash):
        from .git import GitRepository
        state = Store(self.root).state
        decision = decision_document(state)
        if not decision["head"] or decision_hash != decision["decision_hash"]:
            raise Closed("Displayed decision changed; reload before reading diff")
        repo = GitRepository(self.root / "product.git", state["policy"]["base_branch"])
        return {"decision_hash": decision_hash, "base": decision["base"], "head": decision["head"],
                "diff": repo.text("diff", "--no-ext-diff", "--no-textconv", decision["base"], decision["head"], "--")}
