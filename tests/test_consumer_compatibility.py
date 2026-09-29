"""Source compatibility overlays run in disposable archives, never original repos."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("consumer_compatibility", ROOT / "scripts/check_consumer.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class ConsumerCompatibilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.consumer = self.root / "consumer"
        self.source.mkdir()
        self.consumer.mkdir()
        for root, value in ((self.source, "new"), (self.consumer, "old")):
            (root / "control_plane_core").mkdir()
            (root / "control_plane_core/__init__.py").write_text(
                '__version__ = "1.10.0"\nCONTRACT = "autonomous-control-plane/v1"\nVALUE = ' + repr(value) + '\n')
            (root / "scripts").mkdir()
        (self.source / "agent_worker").mkdir()
        (self.source / "agent_worker/__init__.py").write_text('VALUE = "worker"\n')
        executable = self.source / "scripts/check_workflow_adapters.py"
        executable.write_text("#!/usr/bin/env python3\n")
        executable.chmod(0o755)
        (self.consumer / "control_plane_core/obsolete.py").write_text("# old module\n")
        (self.consumer / "scripts/check_workflow_adapters.py").write_text("# old unmanaged tooling\n")
        (self.consumer / "tests").mkdir()
        self.test_file = self.consumer / "tests/test_overlay.py"
        self.test_file.write_text('''import os
from pathlib import Path
import unittest
import control_plane_core
import agent_worker
class Overlay(unittest.TestCase):
    def test_new_portable_source(self):
        self.assertEqual(control_plane_core.VALUE, "new")
        self.assertEqual(agent_worker.VALUE, "worker")
        self.assertFalse(Path("control_plane_core/obsolete.py").exists())
        self.assertTrue(os.access("scripts/check_workflow_adapters.py", os.X_OK))
''')
        for args in (("init", "-q"), ("config", "user.name", "Compatibility fixture"),
                     ("config", "user.email", "fixture@example.invalid")):
            self.git(*args)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.consumer), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", "Trusted consumer fixture")
        return self.git("rev-parse", "HEAD")

    def run_gate(self):
        commit = self.commit()
        before = {p.relative_to(self.consumer).as_posix(): p.read_bytes()
                  for p in self.consumer.rglob("*") if p.is_file() and ".git" not in p.parts}
        with patch.object(gate, "ROOT", self.source):
            report = gate.check_consumer(self.consumer, commit, self.root / "report.json", timeout=30)
        after = {p.relative_to(self.consumer).as_posix(): p.read_bytes()
                 for p in self.consumer.rglob("*") if p.is_file() and ".git" not in p.parts}
        self.assertEqual(before, after)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(json.loads((self.root / "report.json").read_text()), report)
        return report

    def test_unmanaged_archive_is_overlaid_without_weakening_normal_sync(self):
        report = self.run_gate()
        self.assertTrue(report["passed"], (self.root / "report.log").read_text())
        self.assertEqual(report["tests"], 1)
        self.assertTrue(report["snapshot_lock_valid"])
        self.assertFalse(report["release_validation"])
        self.assertIn("agent_worker/__init__.py", report["core_files"])

    def test_legacy_lock_and_manifest_are_replaced_only_in_snapshot(self):
        (self.consumer / gate.LOCK).write_text(json.dumps({"schema": 1, "old": "source binding"}))
        original = b'{"stale": true}\n'
        (self.consumer / "RELEASE-MANIFEST.json").write_bytes(original)
        (self.consumer / "scripts/build_release_manifest.py").write_text('''import hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
files={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
       for p in root.rglob("*") if p.is_file() and p.name != "RELEASE-MANIFEST.json"}
(root/"RELEASE-MANIFEST.json").write_text(json.dumps({"files":files}, sort_keys=True))
''')
        with self.test_file.open("a") as stream:
            stream.write('''    def test_generated_snapshot_manifest(self):
        import hashlib, json
        files=json.loads(Path("RELEASE-MANIFEST.json").read_text())["files"]
        for name, expected in files.items():
            self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), expected)
''')
        report = self.run_gate()
        self.assertTrue(report["passed"], (self.root / "report.log").read_text())
        preparation = report["snapshot_metadata_preparation"][0]
        self.assertEqual(preparation["original_sha256"], hashlib.sha256(original).hexdigest())
        self.assertNotEqual(preparation["snapshot_sha256"], preparation["original_sha256"])
        self.assertEqual(report["tests"], 2)

    def test_changed_snapshot_lock_cannot_be_reported_as_compatible(self):
        with self.test_file.open("a") as stream:
            stream.write('''    def test_change_binding(self):
        Path("CONTROL-CORE.lock.json").write_text("{}")
''')
        report = self.run_gate()
        self.assertFalse(report["passed"])
        self.assertFalse(report["snapshot_lock_valid"])
        self.assertEqual(report["exit_code"], 0)

    def test_zero_test_run_cannot_pass_compatibility(self):
        self.test_file.write_text("# no executable tests\n")
        report = self.run_gate()
        self.assertFalse(report["passed"])
        self.assertEqual(report["tests"], 0)


if __name__ == "__main__":
    unittest.main()
