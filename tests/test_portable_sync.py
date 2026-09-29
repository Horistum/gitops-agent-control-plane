"""Exercise portable source transfer using real independent Git repositories."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("portable_transfer", ROOT / "scripts/sync_control_core.py")
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)
REFERENCE = "Horistum/gitops-agent-control-plane"
FLOW = "Horistum/FlowAi-control"


class PortableTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.repository("source")
        self.target = self.root / "target"
        self.target.mkdir()

    def git(self, root, *args):
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE).decode().strip()

    def repository(self, name):
        root = self.root / name
        root.mkdir()
        self.git(root, "init", "-q")
        self.git(root, "config", "user.name", "Portable fixture")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        (root / "control_plane_core").mkdir()
        (root / "control_plane_core/__init__.py").write_text(
            '__version__ = "1.10.0"\nCONTRACT = "autonomous-control-plane/v1"\n')
        (root / "control_plane_core/LICENSE.md").write_text("Preserved fixture license\n")
        (root / "control_plane_core/NOTICE.md").write_text("Preserved fixture attribution\n")
        (root / ".gitignore").write_text("__pycache__/\n")
        return root

    def commit(self, root):
        self.git(root, "add", ".")
        self.git(root, "commit", "-qm", "Portable fixture")
        return self.git(root, "rev-parse", "HEAD")

    def transfer(self, repository=REFERENCE):
        sha = self.commit(self.source)
        transfer.record(self.source, sha, repository)
        return transfer.sync(self.source, self.target, sha, repository)

    def test_round_trip_development_to_reference_preserves_exact_bytes_and_origin(self):
        initial = self.transfer()
        self.assertEqual(initial["repository"], REFERENCE)
        self.git(self.target, "init", "-q")
        self.git(self.target, "config", "user.name", "Flow fixture")
        self.git(self.target, "config", "user.email", "fixture@example.invalid")
        (self.target / "control_plane_core/authorization.py").write_text("PURPOSE = 'work-plan/v1'\n")
        (self.target / "agent_worker").mkdir()
        (self.target / "agent_worker/__init__.py").write_text('PROFILE = "brokered-session/v1"\n')
        sha = self.commit(self.target)
        transfer.record(self.target, sha, FLOW)
        result = transfer.sync(self.target, self.source, sha, FLOW, adopt_identical=False)
        self.assertEqual(result["repository"], FLOW)
        self.assertEqual(result["commit"], sha)
        self.assertEqual(transfer.inventory(self.source), transfer.inventory(self.target))
        self.assertEqual(result["packages"], ["control_plane_core", "agent_worker"])
        self.assertEqual((self.source / "control_plane_core/LICENSE.md").read_text(), "Preserved fixture license\n")

    def test_initial_canonical_reference_requires_identical_adoption(self):
        sha = self.commit(self.source)
        shutil.copytree(self.source / "control_plane_core", self.target / "control_plane_core")
        with self.assertRaisesRegex(ValueError, "Unmanaged"):
            transfer.sync(self.source, self.target, sha, FLOW)
        transfer.sync(self.source, self.target, sha, FLOW, adopt_identical=True)
        self.assertEqual(transfer.check(self.target)["commit"], sha)

    def test_dirty_or_wrong_source_cannot_mutate_target(self):
        sha = self.commit(self.source)
        path = self.source / "control_plane_core/NOTICE.md"
        path.write_text("Uncommitted change")
        for commit in (sha, "0" * 40):
            with self.assertRaises(ValueError):
                transfer.sync(self.source, self.target, commit)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_target_drift_cannot_be_discarded_even_with_adopt_flag(self):
        self.transfer()
        path = self.target / "control_plane_core/NOTICE.md"
        path.write_text("Local work must survive")
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            transfer.sync(self.source, self.target, self.git(self.source, "rev-parse", "HEAD"),
                          FLOW, adopt_identical=True)
        self.assertEqual(path.read_bytes(), before)

    def test_same_bytes_can_record_new_provenance_without_rewriting_commit_identity(self):
        self.transfer()
        sha = self.git(self.source, "rev-parse", "HEAD")
        value = transfer.record(self.source, sha, FLOW)
        self.assertEqual(value["commit"], sha)
        self.assertEqual(self.git(self.source, "rev-parse", "HEAD"), sha)

    def test_unknown_repository_and_short_commit_rejected(self):
        sha = self.commit(self.source)
        for repository, commit in (("attacker/example", sha), (FLOW, sha[:12])):
            with self.assertRaises(ValueError):
                transfer.sync(self.source, self.target, commit, repository)
        self.assertFalse((self.target / transfer.LOCK).exists())

    def test_source_and_target_symlinks_rejected_before_changes(self):
        self.transfer()
        outside = self.root / "outside"
        outside.mkdir()
        (self.source / "agent_worker").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            transfer.snapshot(self.source, self.git(self.source, "rev-parse", "HEAD"), FLOW)
        (self.source / "agent_worker").unlink()
        (self.target / "control_plane_core/NOTICE.md").unlink()
        (self.target / "control_plane_core/NOTICE.md").symlink_to(outside / "untouched")
        with self.assertRaises(ValueError):
            transfer.sync(self.source, self.target, self.git(self.source, "rev-parse", "HEAD"))
        self.assertEqual(list(outside.iterdir()), [])

    def test_failed_write_restores_previous_inventory_and_lock(self):
        self.transfer()
        old = transfer.check(self.target)
        (self.source / "control_plane_core/new.py").write_text("VALUE = 1\n")
        sha = self.commit(self.source)
        original = transfer.atomic_write
        failed = []
        def once(path, content, mode=0o644):
            if path.name == "new.py" and not failed:
                failed.append(True)
                raise OSError("Injected disk failure")
            return original(path, content, mode)
        with patch.object(transfer, "atomic_write", side_effect=once):
            with self.assertRaises(OSError):
                transfer.sync(self.source, self.target, sha)
        self.assertEqual(transfer.check(self.target), old)
        self.assertFalse((self.target / "control_plane_core/new.py").exists())

    def test_portable_tooling_is_locked_and_exported(self):
        for relative in transfer.TOOLING:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# trusted portable fixture: " + relative + "\n")
        result = self.transfer()
        self.assertTrue(set(transfer.TOOLING) <= set(result["files"]))
        for relative in transfer.TOOLING:
            self.assertEqual((self.target / relative).read_bytes(), (self.source / relative).read_bytes())
        (self.target / "scripts/sync_control_core.py").write_text("# changed\n")
        with self.assertRaises(ValueError):
            transfer.check(self.target)

    def test_legacy_lock_remains_readable_without_claiming_worker_coverage(self):
        self.transfer()
        value = transfer.check(self.target)
        value["schema"] = 1
        value.pop("packages")
        (self.target / transfer.LOCK).write_text(json.dumps(value))
        self.assertEqual(transfer.check(self.target)["schema"], 1)
        (self.target / "agent_worker").mkdir()
        (self.target / "agent_worker/__init__.py").write_text("# untracked local worker\n")
        with self.assertRaises(ValueError):
            transfer.sync(self.source, self.target, self.git(self.source, "rev-parse", "HEAD"))

    def test_tracked_ignored_file_cannot_escape_source_inventory(self):
        (self.source / "control_plane_core/__pycache__").mkdir()
        hidden = self.source / "control_plane_core/__pycache__/hidden.py"
        hidden.write_text("# tracked but deliberately absent from package inventory\n")
        self.git(self.source, "add", "-f", str(hidden))
        sha = self.commit(self.source)
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            transfer.sync(self.source, self.target, sha)

    def test_partial_unmanaged_target_is_preserved(self):
        sha = self.commit(self.source)
        (self.target / "agent_worker").mkdir()
        path = self.target / "agent_worker/__init__.py"
        path.write_text("Local work\n")
        with self.assertRaisesRegex(ValueError, "partial portable"):
            transfer.sync(self.source, self.target, sha)
        self.assertEqual(path.read_text(), "Local work\n")

    def test_empty_optional_package_does_not_invent_lock_coverage(self):
        (self.source / "agent_worker").mkdir()
        result = self.transfer()
        self.assertEqual(result["packages"], ["control_plane_core"])
        self.assertEqual(transfer.check(self.source)["packages"], ["control_plane_core"])

    def test_file_to_directory_collision_is_rejected_before_any_write(self):
        path = self.source / "control_plane_core/group.py"
        path.write_text("# existing module\n")
        self.transfer()
        before = transfer.check(self.target)
        path.unlink()
        path.mkdir()
        (path / "nested.py").write_text("# replacement package\n")
        (self.source / "control_plane_core/NOTICE.md").write_text("Changed notice\n")
        sha = self.commit(self.source)
        with self.assertRaisesRegex(ValueError, "ancestor is not a directory"):
            transfer.sync(self.source, self.target, sha)
        self.assertEqual(transfer.check(self.target), before)
        self.assertEqual((self.target / "control_plane_core/group.py").read_text(), "# existing module\n")


if __name__ == "__main__":
    unittest.main()
