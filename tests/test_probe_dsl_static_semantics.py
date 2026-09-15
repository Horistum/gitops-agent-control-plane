from __future__ import annotations

from copy import deepcopy
import unittest

from reference_runtime.probe_dsl import ProbeContractError, validate_probe


BASE_PROBE = {
    "id": "static-check",
    "target": "src/reference_app/service.py",
    "callable": "greet",
    "cases": {
        "count": 1,
        "args": [{"kind": "constant", "value": "Ada"}],
        "kwargs": [],
    },
    "oracle": {
        "kind": "return-equals",
        "expected": {"op": "arg", "index": 0},
    },
}


class ProbeDslStaticSemanticTests(unittest.TestCase):
    def test_arg_index_is_checked_against_case_arity(self):
        probe = deepcopy(BASE_PROBE)
        probe["oracle"]["expected"] = {"op": "arg", "index": 7}
        with self.assertRaisesRegex(ProbeContractError, "out of range"):
            validate_probe(probe)

    def test_kwarg_reference_must_exist(self):
        probe = deepcopy(BASE_PROBE)
        probe["oracle"]["expected"] = {"op": "kwarg", "name": "missing"}
        with self.assertRaisesRegex(ProbeContractError, "not defined"):
            validate_probe(probe)

    def test_length_rejects_statically_unsized_value(self):
        probe = deepcopy(BASE_PROBE)
        probe["oracle"]["expected"] = {
            "op": "length",
            "value": {"op": "literal", "value": 5},
        }
        with self.assertRaisesRegex(ProbeContractError, "must be sized"):
            validate_probe(probe)

    def test_expression_nesting_is_bounded_before_runtime(self):
        expr = {"op": "arg", "index": 0}
        for _ in range(80):
            expr = {"op": "strip", "value": expr}
        probe = deepcopy(BASE_PROBE)
        probe["oracle"]["expected"] = expr
        with self.assertRaisesRegex(ProbeContractError, "nesting exceeds"):
            validate_probe(probe)

    def test_valid_expression_still_accepts_multi_argument_and_kwarg_context(self):
        probe = deepcopy(BASE_PROBE)
        probe["cases"]["args"] = [
            {"kind": "constant", "value": "Ada"},
            {"kind": "constant", "value": "Lovelace"},
        ]
        probe["cases"]["kwargs"] = [
            {"name": "suffix", "generator": {"kind": "constant", "value": "!"}}
        ]
        probe["oracle"]["expected"] = {
            "op": "concat",
            "parts": [
                {"op": "arg", "index": 0},
                {"op": "literal", "value": " "},
                {"op": "arg", "index": 1},
                {"op": "kwarg", "name": "suffix"},
            ],
        }
        validate_probe(probe)


if __name__ == "__main__":
    unittest.main()
