from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from reference_runtime.contracts import load_json, validate_goal, validate_policy
from reference_runtime.events import EventLog

ROOT = Path(__file__).resolve().parents[1]


class ReferenceRuntimeTests(unittest.TestCase):
    def test_contract_documents_validate(self):
        validate_goal(load_json(ROOT / "examples" / "goal.example.json"))
        validate_policy(load_json(ROOT / "config" / "reference-policy.json"))

    def test_event_chain_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "events.jsonl"
            log = EventLog(path)
            first = log.append("one", {"x": 1})
            second = log.append("two", {"x": 2})
            seq, tip = EventLog.verify(path)
            self.assertEqual(seq, 2)
            self.assertEqual(tip, second["hash"])
            self.assertEqual(second["previous_hash"], first["hash"])

    def test_event_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "events.jsonl"
            log = EventLog(path)
            log.append("one", {"x": 1})
            log.append("two", {"x": 2})
            text = path.read_text().replace('"x": 2', '"x": 99')
            path.write_text(text)
            with self.assertRaises(ValueError):
                EventLog.verify(path)


if __name__ == "__main__":
    unittest.main()
