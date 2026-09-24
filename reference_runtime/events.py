from __future__ import annotations

import json
import os
from pathlib import Path
from .contracts import sha256_json


class EventLog:
    """Append-only-in-normal-use hash chain.

    The chain detects corruption or un-rehashed edits. It is NOT an authenticity
    mechanism: anyone able to rewrite the complete evidence directory can
    recompute it. Production implementations need an external/signature anchor.
    """
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size:
            self.seq, self.tip = self.verify(self.path)
        else:
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
            stream.flush()
            os.fsync(stream.fileno())
        self.seq = event["seq"]
        self.tip = event["hash"]
        return event

    @staticmethod
    def verify(path: Path) -> tuple[int, str]:
        seq = 0
        tip = "0" * 64
        for line_no, raw in enumerate(path.read_text().splitlines(), 1):
            event = json.loads(raw)
            expected_base = {
                "seq": seq + 1,
                "type": event["type"],
                "payload": event["payload"],
                "previous_hash": tip,
            }
            expected_hash = sha256_json(expected_base)
            if event["seq"] != seq + 1 or event["previous_hash"] != tip or event["hash"] != expected_hash:
                raise ValueError(f"event chain verification failed at line {line_no}")
            seq = event["seq"]
            tip = event["hash"]
        return seq, tip
