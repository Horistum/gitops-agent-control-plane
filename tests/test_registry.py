from pathlib import Path
import tempfile
import unittest

from agent_runtime.controller import Controller
from agent_runtime.io import Closed, atomic_json
from agent_runtime.registry import discover_runs, registry_status
from runtime_support import build_product, goal, policy


class RegistryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def make_run(self, name, *, two=False):
        product = self.root / (name + "-product")
        build_product(product, two=two)
        return Controller.start(self.root / "runs" / name, policy(product), goal(two=two), trusted_local=True)

    def test_discover_runs_finds_only_immediate_run_directories(self):
        self.make_run("alpha")
        self.make_run("beta")
        (self.root / "runs" / "not-a-run").mkdir()
        found = discover_runs(self.root / "runs")
        self.assertEqual([p.name for p in found], ["alpha", "beta"])

    def test_discover_runs_accepts_a_single_run_root_directly(self):
        engine = self.make_run("solo")
        self.assertEqual(discover_runs(engine.root), [engine.root.resolve()])

    def test_discover_runs_skips_symlinked_children_and_is_bounded(self):
        self.make_run("real")
        (self.root / "runs" / "linked").symlink_to(self.root / "runs" / "real")
        found = discover_runs(self.root / "runs")
        self.assertEqual([p.name for p in found], ["real"])
        with self.assertRaises(Closed):
            discover_runs(self.root / "runs", limit=0)

    def test_discover_runs_rejects_a_missing_root(self):
        with self.assertRaises(Closed):
            discover_runs(self.root / "does-not-exist")

    def test_registry_status_aggregates_and_isolates_one_broken_run(self):
        alpha = self.make_run("alpha")
        alpha.tick()
        self.make_run("beta")
        atomic_json(self.root / "runs" / "beta" / "state.json", {"not": "a valid run state"})

        report = registry_status(self.root / "runs")
        self.assertEqual(report["run_count"], 2)
        by_root = {Path(row["root"]).name: row for row in report["runs"]}
        self.assertTrue(by_root["alpha"]["readable"])
        self.assertEqual(by_root["alpha"]["run_id"], alpha.state["run_id"])
        self.assertFalse(by_root["beta"]["readable"])
        self.assertIn("reason", by_root["beta"])

    def test_registry_status_on_empty_directory_is_zero_runs_not_an_error(self):
        (self.root / "runs").mkdir()
        self.assertEqual(registry_status(self.root / "runs"), {
            "schema": 1, "root": str((self.root / "runs").resolve()), "run_count": 0, "runs": []})


if __name__ == "__main__":
    unittest.main()
