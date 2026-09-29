"""Portable controller-brokered workers; no repository adapter dependencies."""
from .protocol import WorkerError, WorkerIndeterminate, canonical, fingerprint
from .broker import SourceBroker

__all__ = ["AppServerWorker", "SourceBroker", "WorkerError", "WorkerIndeterminate", "canonical", "fingerprint"]

def __getattr__(name):
    if name == "AppServerWorker":
        from .transport import AppServerWorker
        return AppServerWorker
    raise AttributeError(name)
