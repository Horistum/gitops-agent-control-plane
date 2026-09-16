"""Supported JSON Schema vocabulary agrees with Draft 2020-12 semantics.

The optional third-party comparison is mandatory in CI, with --require-reference.
It is deliberately separate from the zero-dependency runtime validation command.
"""
import copy
import json
from pathlib import Path
import sys
import unittest

from reference_runtime.schema_validation import SchemaValidationError, load_schema, validate_instance

ROOT = Path(__file__).resolve().parents[1]
try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

CASES = [
    ({"const": 1}, True, False), ({"const": True}, 1, False),
    ({"const": {"x": [1]}}, {"x": [True]}, False),
    ({"const": 1}, 1.0, True), ({"enum": [0, 1]}, True, False),
    ({"type": "integer"}, 1.0, True), ({"type": "integer"}, True, False),
    ({"type": "integer"}, 1.5, False),
    ({"uniqueItems": True}, [1, 1.0], False),
    ({"uniqueItems": True}, [1, True], True),
    ({"uniqueItems": True}, [{"x": [1]}, {"x": [1.0]}], False),
    ({"pattern": "cat"}, "a cat walks", True),
    ({"pattern": "^cat$"}, "a cat", False),
    ({"type": ["string", "null"]}, None, True),
    ({"type": "object", "required": ["x"], "additionalProperties": False,
      "properties": {"x": {"type": "number", "minimum": 0}}}, {"x": -1}, False),
]


def accepted(instance, schema):
    try:
        validate_instance(instance, schema)
        return True
    except SchemaValidationError:
        return False


class SchemaSemanticsTests(unittest.TestCase):
    def test_json_equality_integer_and_pattern_semantics(self):
        for schema, value, expected in CASES:
            with self.subTest(schema=schema, instance=value):
                self.assertEqual(accepted(value, schema), expected)

    def test_direct_calls_reject_unsupported_keywords_even_in_unused_branches(self):
        for schema in ({"oneOf": [{}]}, {"properties": {"unused": {"$ref": "x"}}},
                       {"items": {"not": {}}}, {"type": "invented"},
                       {"required": "x"}, {"minimum": True}, {"minItems": -1},
                       {"uniqueItems": "true"}, {"pattern": "["}):
            with self.subTest(schema=schema), self.assertRaises(SchemaValidationError):
                validate_instance({}, schema)

    def test_nonfinite_numbers_cannot_enter_json_evidence(self):
        for value in (float("nan"), float("inf"), {"nested": float("nan")}):
            with self.assertRaises(SchemaValidationError):
                validate_instance(value, {})

    def test_published_hash_patterns_remain_full_string_constraints(self):
        schema = load_schema(ROOT / "schemas" / "event.schema.json")
        for child in schema["properties"].values():
            if "pattern" in child:
                self.assertTrue(accepted("a" * 64, child))
                for invalid in ("x" + "a" * 64, "a" * 65, "a" * 64 + "\n"):
                    self.assertFalse(accepted(invalid, child))


@unittest.skipUnless(Draft202012Validator, "optional jsonschema comparator not installed")
class StandardValidatorComparison(unittest.TestCase):
    def test_supported_semantics_agree(self):
        for schema, value, _ in CASES:
            with self.subTest(schema=schema, instance=value):
                Draft202012Validator.check_schema(schema)
                self.assertEqual(accepted(value, schema), Draft202012Validator(schema).is_valid(value))

    def test_every_published_schema_and_static_authority(self):
        for path in (ROOT / "schemas").glob("*.schema.json"):
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(load_schema(path))
        pairs = [("config/contract-set.json", "contract-set"),
                 ("config/reference-policy.json", "policy"),
                 ("config/role-protocols.json", "role-protocols"),
                 ("examples/goal.example.json", "goal")]
        for filename, schema_name in pairs:
            schema = load_schema(ROOT / "schemas" / (schema_name + ".schema.json"))
            value = json.loads((ROOT / filename).read_text())
            self.assertTrue(accepted(value, schema))
            self.assertTrue(Draft202012Validator(schema).is_valid(value))
            for key in schema["required"]:
                invalid = copy.deepcopy(value)
                del invalid[key]
                self.assertFalse(accepted(invalid, schema))
                self.assertFalse(Draft202012Validator(schema).is_valid(invalid))


if __name__ == "__main__":
    if "--require-reference" in sys.argv:
        sys.argv.remove("--require-reference")
        if Draft202012Validator is None:
            raise SystemExit("Install requirements-test.txt: the comparison gate cannot be skipped")
    unittest.main()
