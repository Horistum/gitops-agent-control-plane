from __future__ import annotations
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class PublicationPolicyTests(unittest.TestCase):
    def test_private_security_reporting_policy_is_defined(self):
        text=(ROOT/'.github'/'SECURITY.md').read_text(); self.assertIn('GitHub Private Vulnerability Reporting',text); self.assertIn('Do not open a public GitHub issue',text)
    def test_release_policy_uses_contract_v3_and_separate_semver(self):
        text=(ROOT/'docs'/'RELEASES.md').read_text(); self.assertIn('gitops-agent-control-plane/v3',text); self.assertIn('vMAJOR.MINOR.PATCH',text); self.assertIn('v0.1.0',text); self.assertNotIn('example.invalid',text)
    def test_support_policy_is_explicitly_best_effort(self):
        text=(ROOT/'SUPPORT.md').read_text().lower(); self.assertIn('best-effort',text); self.assertIn('no response-time guarantee',text)
    def test_publication_requires_ten_scenario_clean_room(self):
        text=(ROOT/'docs'/'PUBLICATION.md').read_text(); self.assertIn('ten',text.lower()); self.assertIn('clean-room',text.lower()); self.assertIn('Private Vulnerability Reporting',text)
    def test_notice_year_is_not_hardcoded_to_single_validation_year(self):
        import re; text=(ROOT/'NOTICE').read_text(); self.assertRegex(text,r'Copyright\s+\d{4}(?:-\d{4})?\s+Horistum contributors')
if __name__=='__main__': unittest.main()
