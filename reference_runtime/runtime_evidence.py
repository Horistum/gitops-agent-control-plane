from __future__ import annotations


import json

from .contracts import CORE_CONTRACT, REFERENCE_CONTRACT, RUNTIME_PROFILE, VERIFICATION_PROFILE
from .events import EventLog


class RuntimeEvidenceMixin:
    """Internal controller responsibility; composed only by the public engine."""

    def _role(
        self,
        role: str,
        verdict: str,
        summary: str,
        *,
        item: str | None,
        iteration: int,
        input_refs: list[str],
        output: dict,
    ) -> None:
        protocol = self.role_protocols["roles"][role]
        artifact = {
            "schema": 3,
            "protocol": f"{CORE_CONTRACT}/role/{role}/v1",
            "role": role,
            "item": item,
            "iteration": iteration,
            "verdict": verdict,
            "summary": summary,
            "input_refs": input_refs,
            "output": output,
            "product_write_power": protocol["product_write_power"],
            "effect_power": protocol["effect_power"],
        }
        self.write_json(f"role-{role}.json", artifact)
        if item:
            self.write_json(
                f"role-{role}-{item.lower()}-attempt-{iteration:02d}.json",
                artifact,
            )

    def _control_loop_value(self) -> dict:
        path = self.evidence / "control-loop.json"
        if path.is_file():
            value = json.loads(path.read_text())
            if isinstance(value.get("cycles"), list):
                return value
        return {
            "schema": 1,
            "reference_contract": REFERENCE_CONTRACT,
            "core_contract": CORE_CONTRACT,
            "objective": self.goal["objective"],
            "cycles": [],
            "completed_items": list(self.state.get("completed_items", [])),
            "goal_satisfied": False,
        }

    def _write_control_loop(self) -> None:
        value = self._control_loop_value()
        value["completed_items"] = list(self.state.get("completed_items", []))
        value["goal_satisfied"] = self.state.get("goal_status") == "SATISFIED"
        self.write_json("control-loop.json", value)

    def _append_cycle(self, item: str, attempts: list[dict], result: str) -> None:
        value = self._control_loop_value()
        row = {
            "cycle": self.state["cycle"],
            "item": item,
            "attempts": attempts,
            "result": result,
        }
        if (
            value["cycles"]
            and value["cycles"][-1].get("cycle") == self.state["cycle"]
            and value["cycles"][-1].get("item") == item
        ):
            existing = value["cycles"][-1]
            seen = {attempt["attempt"] for attempt in existing.get("attempts", [])}
            existing.setdefault("attempts", []).extend(
                attempt for attempt in attempts if attempt["attempt"] not in seen
            )
            existing["result"] = result
        else:
            value["cycles"].append(row)
        value["completed_items"] = list(self.state.get("completed_items", []))
        value["goal_satisfied"] = self.state.get("goal_status") == "SATISFIED"
        self.write_json("control-loop.json", value)

    def build_summary(self, **extra) -> dict:
        seq, tip = EventLog.verify(self.evidence / "events.jsonl")
        summary = {
            "schema": 3,
            "reference_contract": REFERENCE_CONTRACT,
            "contracts": {
                "core": CORE_CONTRACT,
                "verification": VERIFICATION_PROFILE,
                "runtime": RUNTIME_PROFILE,
            },
            "run_id": self.run_id,
            "label": self.label,
            "status": self.state["status"],
            "phase": self.state["phase"],
            "goal_status": self.state["goal_status"],
            "event_count": seq,
            "event_tip": tip,
            "base_sha": self.state["base_sha"],
            "candidate_sha": self.state["candidate_sha"],
            "merge_sha": self.state["merge_sha"],
            "risk": self.state["risk"],
            "current_item": self.state["current_item"],
            "cycle": self.state["cycle"],
            "attempt": self.state["attempt"],
            "completed_items": list(self.state["completed_items"]),
            "evidence_directory": str(self.evidence),
            **extra,
        }
        self.write_json("run-summary.json", summary)
        return summary

    def finish(self, status: str, *, phase: str, **extra) -> dict:
        self.state["status"] = status
        self.state["phase"] = phase
        self.event("run-finished", {
            "status": status,
            "phase": phase,
            "goal_status": self.state.get("goal_status"),
        })
        self._write_control_loop()
        return self.build_summary(**extra)
