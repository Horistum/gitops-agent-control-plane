from __future__ import annotations

from pathlib import Path
import re
import json
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicationPolicyTests(unittest.TestCase):
    """Documentation/publication consistency checks, not runtime security proofs."""

    def test_private_security_reporting_policy_is_defined(self):
        text = (ROOT / ".github" / "SECURITY.md").read_text()
        self.assertIn("GitHub Private Vulnerability Reporting", text)
        self.assertIn("Do not open a public GitHub issue", text)

    def test_release_policy_links_canonical_contracts_and_separate_semver(self):
        text = (ROOT / "docs" / "RELEASES.md").read_text()
        self.assertIn("config/contract-set.json", text)
        readme = (ROOT / "README.md").read_text()
        manifest = json.loads((ROOT / "config/contract-set.json").read_text())
        for key, value in manifest.items():
            if key != "schema":
                self.assertIn(value, readme)
        self.assertIn("vMAJOR.MINOR.PATCH", text)
        self.assertNotIn("v0.1.0", (ROOT / "docs" / "PUBLICATION.md").read_text())

    def test_support_policy_is_explicitly_best_effort(self):
        text = " ".join((ROOT / "SUPPORT.md").read_text().lower().split())
        self.assertIn("best-effort", text)
        self.assertIn("no response-time guarantee", text)

    def test_publication_clean_room_tracks_discovered_scenarios(self):
        scenarios = list((ROOT / "examples" / "scenarios").glob("*.json"))
        self.assertGreaterEqual(len(scenarios), 20)
        text = " ".join((ROOT / "docs" / "PUBLICATION.md").read_text().split())
        self.assertIn("all documented conformance scenarios", text)
        self.assertIn("examples/scenarios/", text)

    def test_notice_year_accepts_year_ranges(self):
        self.assertRegex(
            (ROOT / "NOTICE").read_text(),
            re.compile(
                r"Copyright\s+\d{4}(?:-\d{4})?\s+Horistum contributors"
            ),
        )

    def test_agentctl_help_discloses_local_executor_boundary(self):
        completed = subprocess.run(
            [str(ROOT / "scripts" / "agentctl"), "help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("trusted deterministic fixtures only", completed.stdout)
        self.assertIn("NOT a security sandbox", completed.stdout)


if __name__ == "__main__":
    unittest.main()

