from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reference_runtime.contracts import load_json
from reference_runtime.engine import AutonomousEngine, resume_run
from reference_runtime.persistence import atomic_json
from reference_runtime.scenarios import build_request
from reference_runtime.schema_validation import validate_evidence_directory, validate_json_file

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_FIELDS = {
    "base_sha", "actual_first_parent_sha", "actual_second_parent_sha",
    "candidate_identity_matches",
}


class ProcessInterruption(BaseException):
    """Do not let normal runtime error handling consume the test interruption."""


class MergeReceiptRecoveryTests(unittest.TestCase):
    def engine(self, directory):
        return AutonomousEngine(
            ROOT, build_request(ROOT, "happy-path", load_json(ROOT / "examples/goal.example.json")),
            Path(directory),
        )

    def interrupt(self, engine, boundary, *, after=True):
        write = engine.write_json
        event = engine.event

        def write_hook(name, value):
            target = name == boundary and (
                name != "state.json" or value.get("phase") == "POSTMERGE_VERIFY"
            )
            if target and not after:
                raise ProcessInterruption()
            result = write(name, value)
            if target:
                raise ProcessInterruption()
            return result

        def event_hook(kind, payload):
            target = boundary == "effect-consumed" and kind == boundary and payload.get("kind") == "merge"
            if target and not after:
                raise ProcessInterruption()
            event(kind, payload)
            if target:
                raise ProcessInterruption()

        engine.write_json = write_hook
        engine.event = event_hook
        with self.assertRaises(ProcessInterruption):
            engine.run()
        engine.write_json = write
        engine.event = event

    def assert_complete(self, engine):
        summary = resume_run(ROOT, engine.run_dir)
        self.assertEqual((summary["status"], summary["goal_status"]), ("COMPLETED", "SATISFIED"))
        receipt = load_json(engine.evidence / "merge-evidence.json")
        self.assertEqual(receipt, load_json(engine.evidence / "merge-evidence-example-001.json"))
        self.assertEqual(engine._find_merge_effects(receipt["request_hash"]), [receipt["merge_sha"]])
        self.assertTrue(IDENTITY_FIELDS <= receipt.keys())
        self.assertIn("merge-evidence.json", validate_evidence_directory(ROOT, engine.evidence))
        return receipt

    def test_every_receipt_state_boundary_resumes_with_complete_evidence_and_one_merge(self):
        for boundary in ("merge-evidence.json", "merge-evidence-example-001.json",
                         "state.json", "effect-consumed"):
            for after in (False, True):
                with self.subTest(boundary=boundary, after=after), tempfile.TemporaryDirectory() as directory:
                    engine = self.engine(directory)
                    self.interrupt(engine, boundary, after=after)
                    state = load_json(engine.evidence / "state.json")
                    self.assertIn(state["phase"], {"MERGE_PENDING", "POSTMERGE_VERIFY"})
                    if state["phase"] == "POSTMERGE_VERIFY":
                        self.assertIsNone(state["pending_effect"])
                        for name in ("merge-evidence.json", "merge-evidence-example-001.json"):
                            validate_json_file(engine.evidence / name, ROOT / "schemas/merge-evidence.schema.json")
                    self.assert_complete(engine)

    def test_legacy_or_missing_receipt_projections_are_reconstructed_from_exact_intent(self):
        for alteration in ("legacy", "missing-canonical", "missing-item", "missing-both"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                engine = self.engine(directory)
                self.interrupt(engine, "effect-consumed")
                names = ("merge-evidence.json", "merge-evidence-example-001.json")
                for index, name in enumerate(names):
                    path = engine.evidence / name
                    if alteration == "legacy":
                        value = load_json(path)
                        atomic_json(path, {key: field for key, field in value.items() if key not in IDENTITY_FIELDS})
                    elif alteration == "missing-both" or alteration == ("missing-canonical", "missing-item")[index]:
                        path.unlink()
                self.assert_complete(engine)

    def test_contradictory_or_malformed_evidence_blocks_completion(self):
        for alteration in ("parent", "candidate", "request-hash", "false-match", "malformed",
                           "intent-hash", "intent-state", "missing-intent", "extra-field", "bad-type",
                           "null-receipt", "array-receipt", "intent-shape"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                engine = self.engine(directory)
                self.interrupt(engine, "effect-consumed")
                receipt_path = engine.evidence / "merge-evidence.json"
                receipt = load_json(receipt_path)
                if alteration == "malformed":
                    receipt_path.write_text("{", encoding="utf-8")
                elif alteration in {"null-receipt", "array-receipt"}:
                    receipt_path.write_text("null" if alteration == "null-receipt" else "[]", encoding="utf-8")
                elif alteration == "intent-shape":
                    (engine.evidence / "merge-intent-example-001.json").write_text("[]", encoding="utf-8")
                elif alteration == "missing-intent":
                    (engine.evidence / "merge-intent-example-001.json").unlink()
                elif alteration in {"intent-hash", "intent-state"}:
                    for name in ("merge-intent.json", "merge-intent-example-001.json"):
                        value = load_json(engine.evidence / name)
                        value["request_hash" if alteration == "intent-hash" else "base_sha"] = "0" * (64 if alteration == "intent-hash" else 40)
                        atomic_json(engine.evidence / name, value)
                else:
                    key, value = {
                        "parent": ("actual_first_parent_sha", "0" * 40),
                        "candidate": ("candidate_sha", "0" * 40),
                        "request-hash": ("request_hash", "0" * 64),
                        "false-match": ("candidate_identity_matches", False),
                        "extra-field": ("unknown", "not authorized"),
                        "bad-type": ("effect_occurrences", True),
                    }[alteration]
                    receipt[key] = value
                    atomic_json(receipt_path, receipt)
                before = receipt_path.read_bytes()
                summary = resume_run(ROOT, engine.run_dir)
                self.assertEqual(summary["status"], "BLOCKED_POLICY")
                self.assertNotEqual(summary["goal_status"], "SATISFIED")
                self.assertEqual(receipt_path.read_bytes(), before)
                release = load_json(engine.workspace / ".agent-control/release-state.json")
                self.assertEqual(release["completed"], [])

    def test_receipt_reconstruction_is_itself_restartable(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.engine(directory)
            self.interrupt(engine, "effect-consumed")
            (engine.evidence / "merge-evidence.json").unlink()
            restored = AutonomousEngine.resume_engine(ROOT, engine.run_dir)
            write = restored.write_json

            def crash_after_canonical(name, value):
                result = write(name, value)
                if name == "merge-evidence.json":
                    raise ProcessInterruption()
                return result

            restored.write_json = crash_after_canonical
            with self.assertRaises(ProcessInterruption):
                restored.recover_phase()
            self.assert_complete(engine)

    def test_named_crash_remains_after_complete_receipt_and_durable_state(self):
        from reference_runtime.base import InjectedCrash
        with tempfile.TemporaryDirectory() as directory:
            engine = self.engine(directory)
            engine.request["fault_injection"] = "after-merge-receipt-before-postmerge"
            with self.assertRaises(InjectedCrash):
                engine.run()
            self.assertEqual(load_json(engine.evidence / "state.json")["phase"], "POSTMERGE_VERIFY")
            for name in ("merge-evidence.json", "merge-evidence-example-001.json"):
                validate_json_file(engine.evidence / name, ROOT / "schemas/merge-evidence.schema.json")
            self.assert_complete(engine)


class AtomicEvidenceTests(unittest.TestCase):
    def test_replace_failure_preserves_previous_json_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            atomic_json(path, {"phase": "MERGE_PENDING"})
            with patch("reference_runtime.persistence.os.replace", side_effect=OSError("interrupted replace")):
                with self.assertRaises(OSError):
                    atomic_json(path, {"phase": "POSTMERGE_VERIFY"})
            self.assertEqual(load_json(path), {"phase": "MERGE_PENDING"})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_file_and_directory_are_synced_around_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            order = []
            import os
            replace = os.replace
            with patch("reference_runtime.persistence.os.fsync", side_effect=lambda fd: order.append("sync")), \
                 patch("reference_runtime.persistence.os.replace", side_effect=lambda *args: (order.append("replace"), replace(*args))):
                atomic_json(Path(directory) / "state.json", {"phase": "POSTMERGE_VERIFY"})
            self.assertEqual(order, ["sync", "replace", "sync"])


if __name__ == "__main__":
    unittest.main()
