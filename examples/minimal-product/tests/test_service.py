from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_app.service import normalize_name


class NormalizeNameTests(unittest.TestCase):
    def test_trims_and_collapses_whitespace(self):
        self.assertEqual(normalize_name("  Ada   Lovelace "), "Ada Lovelace")

    def test_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            normalize_name("   ")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            normalize_name(None)


if __name__ == "__main__":
    unittest.main()
