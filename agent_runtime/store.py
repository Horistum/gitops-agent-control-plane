"""Single-writer state, immutable effect receipts and explicit uncertain calls."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
import re
import control_plane_core
from control_plane_core import fingerprint, model_call_action
from .io import Closed, NotDispatched, atomic_json, digest, read_json


def runtime_fingerprint():
    roots = [Path(__file__).parent, Path(control_plane_core.__file__).parent]
    files = {root.name + "/" + path.relative_to(root).as_posix(): digest(path.read_bytes())
             for root in roots for path in sorted(root.rglob("*.py"))}
    return fingerprint(files)


def validate_authority(state):
    from .contracts import validate_configuration
    validate_configuration(state["policy"], state["goal"])
    if state["policy_hash"] != fingerprint({"policy": state["policy"], "goal": state["goal"]}):
        raise Closed("Saved authority snapshot changed", code="AUTHORITY_CHANGED")


class Store:
    def __init__(self, root, state=None):
        self.root = Path(root)
        self.path = self.root / "state.json"
        self.state = state if state is not None else read_json(self.path, maximum=64_000_000)
        if not isinstance(self.state, dict):
            raise Closed("Run state must be a JSON object")
        self.after_receipt = lambda _: None  # Fault-injection seam; never policy input.

    def save(self):
        self.state["revision"] = self.state.get("revision", 0) + 1
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        if self.state.get("task"):
            self.state["phase"] = self.state["task"]["phase"]
        self.state["history"] = self.state.get("history", [])[-1000:]
        atomic_json(self.path, self.state)

    def read_receipt(self, identity):
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise Closed("Invalid effect identity")
        try:
            value = read_json(self.root / "receipts" / (identity + ".json"))
        except FileNotFoundError:
            raise Closed("Recorded effect receipt is missing; restore evidence before continuing", code="RECEIPT_MISSING") from None
        if not isinstance(value, dict):
            raise Closed("Effect receipt must be an object")
        request = value.get("request")
        if (not isinstance(request, dict) or fingerprint(request) != identity
                or request.get("run_id") != self.state["run_id"]
                or value.get("output_hash") != fingerprint(value.get("output"))):
            raise Closed("Effect receipt provenance or content differs")
        return value

    def effect(self, kind, payload, perform, *, prepare=None):
        task = self.state.get("task") or {}
        request = {"kind": kind, "payload": payload, "policy_hash": self.state["policy_hash"],
                   "runtime_hash": self.state["runtime_hash"], "run_id": self.state["run_id"],
                   "epoch": self.state["effect_epoch"], "item": task.get("id"),
                   "attempt": task.get("attempt"), "turn": task.get("turn", 0)}
        identity = fingerprint(request)
        receipt = self.root / "receipts" / (identity + ".json")
        pending = self.state.get("pending")
        if pending and pending["id"] != identity:
            raise Closed("A different effect remains pending; reconcile it first")
        if receipt.exists():
            value = self.read_receipt(identity)
            if value.get("request") != request:
                raise Closed("Effect receipt provenance or content differs")
            result = value["output"]
        else:
            if identity in self.state.get("receipts", {}):
                raise Closed("Recorded effect receipt is missing; restore it instead of repeating the effect", code="RECEIPT_MISSING")
            if kind == "model" and model_call_action(receipt_available=False,
                    dispatch_state="dispatched" if pending else "not_started") == "hold":
                raise Closed("Indeterminate model call; explicit retry-effect must name " + identity, code="MODEL_OUTCOME_UNKNOWN")
            if not pending:
                if kind == "model" and self.state["model_calls"] >= self.state["policy"]["limits"]["model_calls"]:
                    raise Closed("Model call budget exhausted", code="MODEL_BUDGET_EXHAUSTED")
                # No provider can be called during preparation. Resolve credentials
                # before reserving; a receipt replay never needs current credentials.
                if prepare is not None:
                    prepare()
                if kind == "model":
                    self.state["model_calls"] += 1
                self.state["pending"] = {"id": identity, "kind": kind, "request": request}
                self.save()
            try:
                result = perform(identity)
            except NotDispatched:
                if kind == "model":
                    self.state["model_calls"] -= 1
                    self.state["pending"] = None
                    self.save()
                raise
            value = {"request": request, "output": result, "output_hash": fingerprint(result)}
            atomic_json(receipt, value)
            self.after_receipt(identity)
        if not pending or pending["id"] == identity:
            self.state["pending"] = None
        self.state.setdefault("receipts", {})[identity] = {"kind": kind, "output_hash": fingerprint(result)}
        # Receipt consumption and the resulting phase transition are persisted
        # together by the controller; a crash before save reuses this receipt.
        return copy.deepcopy(result)
