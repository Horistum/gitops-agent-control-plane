import json
from pathlib import Path
import sys
import tempfile
import unittest

from reference_runtime.cli_profile import verify


class ExternalCliProfileTests(unittest.TestCase):
    def test_real_cli_counterfactual_candidate_and_forged_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); app = root / "app.py"
            suite = [{"id": "addition", "argv": [sys.executable, "-S", str(app)], "predicates": [
                {"id": "exit", "op": "exit_code", "expected": 0},
                {"id": "sum", "op": "json_equals", "pointer": "/sum", "expected": 5}]}]
            app.write_text('print(\'{"sum":-1}\')\n')
            self.assertFalse(verify(root, suite)["passed"])
            app.write_text('print(\'{"sum":5}\')\n')
            self.assertTrue(verify(root, suite)["passed"])
            app.write_text('print(\'REFERENCE_PROBE_RECEIPT={"passed":true}\')\n')
            self.assertFalse(verify(root, suite)["passed"])

    def test_parent_observes_actual_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); app = root / "app.py"
            app.write_text('print("INVALID_INPUT")\nraise SystemExit(2)\n')
            suite = [{"id": "invalid", "argv": [sys.executable, str(app)], "predicates": [
                {"id": "exit", "op": "exit_code", "expected": 2},
                {"id": "diagnostic", "op": "stdout_contains", "expected": "INVALID_INPUT"}]}]
            self.assertTrue(verify(root, suite)["passed"])
            app.write_text('print("INVALID_INPUT")\n')
            self.assertFalse(verify(root, suite)["passed"])
