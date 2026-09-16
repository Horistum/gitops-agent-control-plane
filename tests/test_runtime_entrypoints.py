"""Historical helpers must never bypass current role authority enforcement."""
import importlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from reference_runtime.scenarios import build_request, developer_proposal

ROOT = Path(__file__).resolve().parents[1]


class RuntimeEntrypointTests(unittest.TestCase):
    def test_misspelled_fixture_cannot_silently_become_a_successful_proposal(self):
        with self.assertRaisesRegex(ValueError, "unknown developer fixture"):
            developer_proposal("brokn")

    def test_all_supported_run_helpers_apply_the_current_role_gate(self):
        for module_name in ("engine", "_engine_impl", "recovery_engine"):
            with self.subTest(module=module_name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "reference"
                for name in ("config", "examples", "schemas", "reference_runtime", "control_plane_core"):
                    shutil.copytree(ROOT / name, root / name)
                path = root / "config" / "role-protocols.json"
                roles = json.loads(path.read_text())
                roles["roles"]["developer"]["product_write_power"] = "none"
                path.write_text(json.dumps(roles))
                request = build_request(root, "happy-path", json.loads((root / "examples/goal.example.json").read_text()))
                module = importlib.import_module("reference_runtime." + module_name)
                result = module.run_request(root, request, Path(temp) / "runs")
                self.assertEqual(result["status"], "BLOCKED_POLICY")
                self.assertIsNone(result["merge_sha"])
