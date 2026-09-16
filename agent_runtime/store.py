"""Single-writer state, immutable effect receipts and explicit uncertain calls."""
from __future__ import annotations

import copy
from pathlib import Path
import control_plane_core
from control_plane_core import fingerprint
from .io import Closed, atomic_json, digest, read_json


def runtime_fingerprint():
    roots = [Path(__file__).parent, Path(control_plane_core.__file__).parent]
    files = {root.name + "/" + path.relative_to(root).as_posix(): digest(path.read_bytes())
             for root in roots for path in sorted(root.rglob("*.py"))}
    return fingerprint(files)


class Store:
    def __init__(self, root, state=None):
        self.root = Path(root)
        self.path = self.root / "state.json"
        self.state = state if state is not None else read_json(self.path, maximum=64_000_000)
        self.after_receipt = lambda _: None  # Fault-injection seam; never policy input.

    def save(self):
        self.state["history"] = self.state.get("history", [])[-1000:]
        atomic_json(self.path, self.state)

    def effect(self, kind, payload, perform):
        task = self.state.get("task") or {}
        request = {"kind": kind, "payload": payload, "policy_hash": self.state["policy_hash"],
                   "runtime_hash": self.state["runtime_hash"], "run_id": self.state["run_id"],
                   "epoch": self.state["effect_epoch"], "item": task.get("id"),
                   "attempt": task.get("attempt"), "turn": task.get("turn", 0)}
        identity = fingerprint(request)
        receipt = self.root / "receipts" / (identity + ".json")
        pending = self.state.get("pending")
        if receipt.exists():
            value = read_json(receipt)
            if value.get("request") != request or value.get("output_hash") != fingerprint(value.get("output")):
                raise Closed("Effect receipt provenance or content differs")
            result = value["output"]
        else:
            if pending and pending["id"] != identity:
                raise Closed("A different effect remains pending; reconcile it first")
            if pending and kind == "model":
                raise Closed("Indeterminate model call; explicit retry-effect must name " + identity)
            if not pending:
                if kind == "model":
                    if self.state["model_calls"] >= self.state["policy"]["limits"]["model_calls"]:
                        raise Closed("Model call budget exhausted")
                    self.state["model_calls"] += 1
                self.state["pending"] = {"id": identity, "kind": kind, "request": request}
                self.save()
            result = perform(identity)
            value = {"request": request, "output": result, "output_hash": fingerprint(result)}
            atomic_json(receipt, value)
            self.after_receipt(identity)
        if not pending or pending["id"] == identity:
            self.state["pending"] = None
        self.state.setdefault("receipts", {})[identity] = {"kind": kind, "output_hash": fingerprint(result)}
        # Receipt consumption and the resulting phase transition are persisted
        # together by the controller; a crash before save reuses this receipt.
        return copy.deepcopy(result)
