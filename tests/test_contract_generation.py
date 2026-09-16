import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from control_plane_core import CONTRACT, __version__
from reference_runtime.contract_ids import CONTRACT_SET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("generate_contracts", ROOT / "scripts/generate_contracts.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class ContractGenerationTests(unittest.TestCase):
    def test_current_projections_and_package_metadata_match(self):
        import tomllib
        self.assertEqual(generator.drifted_projections(ROOT), [])
        self.assertEqual(CONTRACT, CONTRACT_SET["core_contract"])
        self.assertEqual(__version__, tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"])

    def test_one_manifest_change_projects_every_identity_without_editing_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("config", "schemas", "control_plane_core"):
                shutil.copytree(ROOT / name, root / name)
            shutil.copyfile(ROOT / "README.md", root / "README.md")
            path = root / "config/contract-set.json"
            value = json.loads(path.read_text())
            for key in value:
                if key != "schema":
                    value[key] = value[key].split("/v")[0] + "/v99"
            path.write_text(json.dumps(value))
            self.assertEqual(len(generator.drifted_projections(root)), 7)
            for target, content in generator.projections(root).items():
                target.write_text(json.dumps(content))
            for target, content in generator.text_projections(root).items():
                target.write_text(content)
            self.assertEqual(generator.drifted_projections(root), [])

    def test_portable_package_imports_without_reference_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "control_plane_core", root / "control_plane_core")
            result = subprocess.run([sys.executable, "-S", "-c",
                "from control_plane_core import *; assert CONTRACT; assert next_phase('tester') == 'independent_baseline'"],
                cwd=root, env={"PYTHONPATH": str(root)}, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
