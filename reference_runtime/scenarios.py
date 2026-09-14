from __future__ import annotations

CORRECT_SERVICE = '''
def normalize_name(name: str) -> str:
    """Trim and collapse whitespace in a human-readable name."""
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    normalized = " ".join(name.split())
    if not normalized:
        raise ValueError("name must not be blank")
    return normalized


def greet(name: str) -> str:
    """Return a deterministic greeting using the canonical name normalization."""
    return f"Hello, {normalize_name(name)}!"
'''

BROKEN_SERVICE = '''
def normalize_name(name: str) -> str:
    """Trim and collapse whitespace in a human-readable name."""
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    normalized = " ".join(name.split())
    if not normalized:
        raise ValueError("name must not be blank")
    return normalized


def greet(name: str) -> str:
    """Intentionally broken implementation used by the verification demo."""
    return f"Hi, {normalize_name(name)}!"
'''

INIT_WITH_GREET = '''
from .service import greet, normalize_name

__all__ = ["greet", "normalize_name"]
'''

TESTS_WITH_GREET = '''
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_app.service import greet, normalize_name


class NormalizeNameTests(unittest.TestCase):
    def test_trims_and_collapses_whitespace(self):
        self.assertEqual(normalize_name("  Ada   Lovelace "), "Ada Lovelace")

    def test_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            normalize_name("   ")

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            normalize_name(None)


class GreetingTests(unittest.TestCase):
    def test_greet_reuses_normalization(self):
        self.assertEqual(greet("  Ada   Lovelace "), "Hello, Ada Lovelace!")

    def test_greet_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            greet("   ")


if __name__ == "__main__":
    unittest.main()
'''

SECURITY_GUARD = '''
def privileged_change_marker() -> bool:
    """A harmless file whose path is intentionally classified as critical."""
    return True
'''


def proposal_for(name: str) -> list[dict]:
    if name == "forbidden-path":
        return [
            {
                "path": ".agent-control/architecture.md",
                "content": "# Unauthorized architecture rewrite\n",
                "reason": "Demonstrate that product authority cannot be rewritten by an implementation proposal.",
            }
        ]

    service = BROKEN_SERVICE if name == "test-failure" else CORRECT_SERVICE
    edits = [
        {"path": "src/reference_app/service.py", "content": service, "reason": "Implement EXAMPLE-001."},
        {"path": "src/reference_app/__init__.py", "content": INIT_WITH_GREET, "reason": "Expose the new public API."},
        {"path": "tests/test_service.py", "content": TESTS_WITH_GREET, "reason": "Add independent executable acceptance tests."},
    ]
    if name == "human-gate":
        edits.append(
            {
                "path": "src/reference_app/security/guard.py",
                "content": SECURITY_GUARD,
                "reason": "Exercise critical-path escalation without adding real security behavior.",
            }
        )
    return edits


EXPECTED_OUTCOME = {
    "happy-path": "COMPLETED",
    "forbidden-path": "BLOCKED_POLICY",
    "test-failure": "FAILED_VERIFICATION",
    "human-gate": "NEEDS_DECISION",
    "crash-recovery": "COMPLETED",
}

SUPPORTED = tuple(EXPECTED_OUTCOME)
