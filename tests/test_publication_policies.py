from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicationPolicyTests(unittest.TestCase):
    def test_private_security_reporting_policy_is_defined(self):
        path = ROOT / ".github" / "SECURITY.md"
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn("GitHub Private Vulnerability Reporting", text)
        self.assertIn("Do not open a public GitHub issue", text)
        self.assertIn("hard publication gate", text)

    def test_release_policy_separates_release_and_contract_versions(self):
        path = ROOT / "docs" / "RELEASES.md"
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn("Semantic Versioning", text)
        self.assertIn("gitops-agent-control-plane/v2", text)
        self.assertIn("v0.1.0", text)
        self.assertIn("Release gate", text)
        self.assertRegex(text, r"vMAJOR\.MINOR\.PATCH")

    def test_support_policy_is_explicitly_best_effort(self):
        path = ROOT / "SUPPORT.md"
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn("best-effort", text)
        self.assertIn("does not carry", text)
        self.assertIn("SLA", text)
        self.assertIn(".github/SECURITY.md", text)
        self.assertIn("future commercial Horistum product", text)

    def test_publication_policy_marks_first_three_controls_defined(self):
        text = (ROOT / "docs" / "PUBLICATION.md").read_text()
        for phrase in (
            "Publication controls now defined",
            "Private security reporting",
            "Release and versioning policy",
            "Public support expectations",
            "Remaining publication gates",
        ):
            self.assertIn(phrase, text)

    def test_policy_files_do_not_claim_public_release_exists(self):
        release_text = (ROOT / "docs" / "RELEASES.md").read_text()
        publication_text = (ROOT / "docs" / "PUBLICATION.md").read_text()
        self.assertIn("intended first public release", release_text)
        self.assertIn("After all remaining publication gates pass", publication_text)
        self.assertNotRegex(release_text, re.compile(r"current public release\s*:\s*v", re.I))


if __name__ == "__main__":
    unittest.main()
