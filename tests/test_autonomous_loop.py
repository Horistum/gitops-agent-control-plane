from __future__ import annotations
import json
from pathlib import Path
import tempfile,unittest
from reference_runtime.contracts import CORE_CONTRACT,REFERENCE_CONTRACT,RUNTIME_PROFILE,VERIFICATION_PROFILE,load_json,validate_contract_set,validate_goal,validate_policy
from reference_runtime.engine import AutonomousEngine
from reference_runtime.scenarios import build_request
ROOT=Path(__file__).resolve().parents[1]; PRODUCT=ROOT/'examples'/'minimal-product'
class ContractDecompositionTests(unittest.TestCase):
 def test_contract_set_separates_core_verification_and_runtime(self):
  v=load_json(ROOT/'config'/'contract-set.json'); validate_contract_set(v); self.assertEqual(v['reference_contract'],REFERENCE_CONTRACT); self.assertEqual(v['core_contract'],CORE_CONTRACT); self.assertEqual(v['verification_profile'],VERIFICATION_PROFILE); self.assertEqual(v['runtime_profile'],RUNTIME_PROFILE)
 def test_goal_explicitly_classifies_machine_and_context_fields(self):
  g=load_json(ROOT/'examples'/'goal.example.json'); validate_goal(g); self.assertEqual(g['field_semantics']['objective'],'reasoning_context'); self.assertEqual(g['field_semantics']['items'],'enforced_intent'); self.assertEqual(g['field_semantics']['success_condition'],'verified_projection')
 def test_policy_bounds_goal_autonomy(self):
  p=load_json(ROOT/'config'/'reference-policy.json'); g=load_json(ROOT/'examples'/'goal.example.json'); validate_policy(p); self.assertLessEqual(g['autonomy']['max_cycles'],p['max_cycles']); self.assertLessEqual(g['autonomy']['max_attempts_per_item'],p['max_attempts_per_item'])
class AuthorityAndRoleProtocolTests(unittest.TestCase):
 def test_authority_model(self):
  m=load_json(PRODUCT/'.agent-control'/'authority-model.json'); self.assertEqual(m['artifacts']['roadmap.json']['class'],'intent_authority'); self.assertEqual(m['artifacts']['release-state.json']['mutation'],'controller-after-verified-effect'); self.assertEqual(m['artifacts']['architecture.md']['enforcement'],'reasoning-context')
 def test_role_protocols_have_no_effect_power(self):
  v=load_json(ROOT/'config'/'role-protocols.json'); self.assertEqual(set(v['roles']),{'discovery','architect','developer','test-designer','tester','reviewer'}); self.assertTrue(all(r['effect_power']=='none' for r in v['roles'].values()))
class AutonomousSelectionTests(unittest.TestCase):
 def _engine(self,scenario,directory): return AutonomousEngine(ROOT,build_request(ROOT,scenario,load_json(ROOT/'examples'/'goal.example.json')),Path(directory))
 def test_dependency_selection_unlocks_second_item_only_after_release_state(self):
  with tempfile.TemporaryDirectory() as d:
   e=self._engine('autonomous-two-item',d); self.assertEqual([i['id'] for i in e.eligible_items()],['EXAMPLE-001']); p=e.workspace/'.agent-control'/'release-state.json'; s=json.loads(p.read_text()); s['completed']=['EXAMPLE-001']; s['history']=[{'item':'EXAMPLE-001','verified_merge_sha':'a'*40,'recorded_by':'controller'}]; p.write_text(json.dumps(s)); e.authority=e.load_authority(); self.assertEqual([i['id'] for i in e.eligible_items()],['EXAMPLE-002'])
 def test_repair_catalog_has_two_attempts(self):
  r=build_request(ROOT,'repair-loop',load_json(ROOT/'examples'/'goal.example.json')); self.assertEqual(len(r['work_catalog']['EXAMPLE-001']),2)
 def test_runtime_installs_profile_adapters(self):
  with tempfile.TemporaryDirectory() as d:
   e=self._engine('autonomous-two-item',d); self.assertEqual(e.verification_adapter.profile,RUNTIME_PROFILE); self.assertEqual(e.effect_adapter.profile,RUNTIME_PROFILE)
if __name__=='__main__': unittest.main()
