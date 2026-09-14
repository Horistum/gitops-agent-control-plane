from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicationPolicyTests(unittest.TestCase):
    """Policy/document consistency checks, not runtime-security tests."""

    def test_private_security_reporting_policy_is_defined(self):
        path = ROOT / ".github" / "SECURITY.md"
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn("GitHub Private Vulnerability Reporting", text)
        self.assertIn("Do not open a public GitHub issue", text)

    def test_release_policy_uses_contract_v4_and_separate_semver(self):
        text = (ROOT / "docs" / "RELEASES.md").read_text()
        self.assertIn("gitops-agent-control-plane/v4", text)
        self.assertIn("vMAJOR.MINOR.PATCH", text)
        self.assertIn("v0.1.0", text)

    def test_support_policy_is_explicitly_best_effort(self):
        text = (ROOT / "SUPPORT.md").read_text().lower()
        self.assertIn("best-effort", text)
        self.assertIn("no response-time guarantee", text)

    def test_publication_clean_room_tracks_discovered_scenarios(self):
        scenario_files = sorted((ROOT / "examples" / "scenarios").glob("*.json"))
        self.assertGreaterEqual(len(scenario_files), 13)
        text = (ROOT / "docs" / "PUBLICATION.md").read_text()
        self.assertIn("all documented conformance scenarios", text)
        self.assertIn("examples/scenarios/", text)
        self.assertIn("Private Vulnerability Reporting", text)

    def test_notice_year_accepts_year_ranges(self):
        text = (ROOT / "NOTICE").read_text()
        self.assertRegex(text, re.compile(r"Copyright\s+\d{4}(?:-\d{4})?\s+Horistum contributors"))


if __name__ == "__main__":
    unittest.main()
