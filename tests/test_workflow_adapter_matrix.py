"""Run this adapter's contract matrix without access to another checkout."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workflow_adapter_matrix", ROOT / "scripts/check_workflow_adapters.py")
MATRIX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MATRIX)


class WorkflowAdapterMatrixTests(unittest.TestCase):
    def test_actual_controller_safety_matrix(self):
        profile = "reference" if (ROOT / "agent_runtime").is_dir() else "flow"
        for name in MATRIX.SCENARIOS:
            with self.subTest(scenario=name):
                report = MATRIX.worker(profile, ROOT, ROOT, [name])
                self.assertIn(name, report["scenarios"])


if __name__ == "__main__":
    unittest.main()
