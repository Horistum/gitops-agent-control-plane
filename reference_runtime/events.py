from __future__ import annotations

import json
from pathlib import Path
from .contracts import sha256_json


class EventLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        self.tip = "0" * 64

    def append(self, event_type: str, payload: dict) -> dict:
        base = {
            "seq": self.seq + 1,
            "type": event_type,
            "payload": payload,
            "previous_hash": self.tip,
        }
        event = {**base, "hash": sha256_json(base)}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        self.seq = event["seq"]
        self.tip = event["hash"]
        return event

    @staticmethod
    def verify(path: Path) -> tuple[int, str]:
        seq = 0
        tip = "0" * 64
        for raw in path.read_text().splitlines():
            event = json.loads(raw)
            expected_base = {
                "seq": seq + 1,
                "type": event["type"],
                "payload": event["payload"],
                "previous_hash": tip,
            }
            expected_hash = sha256_json(expected_base)
            if event["seq"] != seq + 1 or event["previous_hash"] != tip or event["hash"] != expected_hash:
                raise ValueError("event chain verification failed")
            seq = event["seq"]
            tip = event["hash"]
        return seq, tip
