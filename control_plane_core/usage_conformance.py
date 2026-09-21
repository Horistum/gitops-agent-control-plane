"""Executable portable contract vectors. Both runtime profiles run these bytes."""
import unittest

from . import CoreError, validate_usage


class UsageConformance(unittest.TestCase):
    def test_valid_usage_is_returned_as_a_plain_dict(self):
        self.assertEqual(validate_usage({}), {})
        self.assertEqual(validate_usage({"input_tokens": 5, "cached_input_tokens": 2}),
                         {"input_tokens": 5, "cached_input_tokens": 2})
        self.assertEqual(validate_usage({"cached_input_tokens": 0, "input_tokens": 0}),
                         {"cached_input_tokens": 0, "input_tokens": 0})

    def test_unsupported_or_malformed_counters_fail_closed(self):
        bad = [
            {"cost": 5}, {"input_tokens": True}, {"output_tokens": -1}, {"input_tokens": 1.5},
            {"input_tokens": 10 ** 12 + 1}, {"cached_input_tokens": 2},
            {"input_tokens": 1, "cached_input_tokens": 2}, "not-a-dict", ["input_tokens"],
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(CoreError):
                validate_usage(value)

    def test_returned_value_is_an_independent_copy(self):
        source = {"input_tokens": 3}
        result = validate_usage(source)
        result["input_tokens"] = 99
        self.assertEqual(source["input_tokens"], 3)


if __name__ == "__main__":
    unittest.main()
