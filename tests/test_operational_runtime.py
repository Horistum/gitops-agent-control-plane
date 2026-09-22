import copy
from pathlib import Path
import tempfile
import unittest

from agent_runtime.actions import action
from agent_runtime.controller import Controller
from agent_runtime.io import Closed
from agent_runtime.store import Store
from runtime_support import build_product, goal, policy, InProcessProvider
from control_plane_core.workflow_conformance import capture_workflow_trace, require_delivery_trace


class OperationalRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name); self.product=self.root/'product'
        build_product(self.product,two=True)
        self.policy=policy(self.product); self.goal=goal()

    def start(self, provider=None):
        engine=Controller.start(self.root/'run',self.policy,self.goal,trusted_local=True)
        if provider:
            engine.reasoning=provider
        return engine

    def drive(self,engine,stop=None,limit=160):
        for _ in range(limit):
            result=engine.tick()
            if stop and result['phase']==stop:
                return result
            if result['status']!='RUNNING':
                return result
        self.fail('controller failed to reach a bounded terminal state')

    def test_real_subprocess_provider_git_tests_two_item_goal_and_retained_regressions(self):
        self.goal=goal(two=True)
        engine=self.start()
        with capture_workflow_trace() as trace:
            result=self.drive(engine)
        require_delivery_trace(trace, challenge=True, cycles=2)
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(result['completed'],['TASK-1','TASK-2'])
        archive=engine.state['archive']
        self.assertIn('TASK1:test_value',archive[1]['baseline']['junit']['executed_identities'])
        for task in archive:
            self.assertEqual(engine.repo.parents(task['merge_sha']),[task['base'],task['head']])
            self.assertTrue(task['obligations']['complete'])
            self.assertTrue(task['acceptance']['passed'])
        self.assertIn('return 2',engine.repo.read(engine.repo.resolve('main'),'other.py').decode())
        self.assertEqual((self.product/'app.py').read_text(),'def value():\n    return 1\n')
        phases={row['phase'] for row in engine.state['history']}
        self.assertTrue({'test_design','chief_plan','independent_baseline','challenge_review','architect_accept','chief_accept','postmerge'} <= phases)

    def test_real_feedback_drives_bounded_developer_repair(self):
        def broken_once(payload,result,_):
            if payload['phase']=='developer' and payload['task']['repairs']==0:
                result['edits'][0]['content']='def value():\n    return 0\n'
        provider=InProcessProvider(broken_once); engine=self.start(provider)
        result=self.drive(engine)
        self.assertEqual(result['status'],'COMPLETED',result)
        attempts=[row for row in provider.calls if row['phase']=='developer']
        self.assertEqual(len(attempts),2)
        self.assertTrue(attempts[1]['task']['feedback'])
        self.assertIn('observation',attempts[1]['task']['feedback'][0])

    def test_independent_tautology_rejected_then_repaired_before_freeze(self):
        def tautology(payload,result,_):
            if payload['phase']=='tester' and payload['task']['repairs']==0:
                result['edits'][0]['content']=result['edits'][0]['content'].replace('self.assertEqual(value(), 2)','self.assertGreater(value(), 0)')
        provider=InProcessProvider(tautology); engine=self.start(provider)
        result=self.drive(engine)
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(len([row for row in provider.calls if row['phase']=='tester']),2)

    def test_tester_cannot_relabel_new_behavior_as_regression(self):
        def weaken(payload,result,_):
            if payload['phase']=='tester':
                result['bindings'][0]['mode']='regression'
                result['edits'][0]['content']=result['edits'][0]['content'].replace('self.assertEqual(value(), 2)','self.assertGreater(value(), 0)')
        engine=self.start(InProcessProvider(weaken)); baseline=engine.repo.resolve('main')
        result=self.drive(engine)
        self.assertEqual(result['status'],'BLOCKED_POLICY',result)
        self.assertIn('criterion type',result['reason'])
        self.assertEqual(engine.repo.resolve('main'),baseline)

    def test_real_provider_schema_failure_is_repaired_without_resetting_call_budget(self):
        import sys
        from runtime_support import ROOT
        wrapper=self.root/'invalid_once.py'; marker=self.root/'called'
        wrapper.write_text('import json,sys\nfrom pathlib import Path\n'
            + 'sys.path.insert(0,' + repr(str(ROOT/'tests')) + ')\n'
            + 'from runtime_support import proposal\n'
            + 'marker=Path(' + repr(str(marker)) + ')\n'
            + 'request=json.load(sys.stdin)\n'
            + 'if not marker.exists():\n    marker.touch(); print("{}")\n'
            + 'else:\n    print(json.dumps(proposal(request["input"])))\n')
        self.policy['reasoning']['argv']=[sys.executable,str(wrapper)]
        engine=self.start(); self.assertEqual(engine.tick()['phase'],'reconcile')
        self.assertEqual(engine.state['model_calls'],1)
        self.assertEqual(engine.state['discovery']['feedback'][0]['kind'],'protocol')
        self.assertEqual(self.drive(engine)['status'],'COMPLETED')

    def test_protected_edit_never_becomes_commit(self):
        def attack(payload,result,_):
            if payload['phase']=='developer':
                result['edits'][0].update(path='.github/workflows/ci.yml',expected_sha256='',content='weaken checks')
        engine=self.start(InProcessProvider(attack)); baseline=engine.repo.resolve('main')
        result=self.drive(engine)
        self.assertEqual(result['status'],'BLOCKED_POLICY',result)
        self.assertEqual(engine.repo.resolve('main'),baseline)
        self.assertEqual(engine.task['head'],baseline)

    def test_human_approval_binds_candidate_and_base_move_blocks_merge(self):
        self.goal=goal(approval=True);engine=self.start(InProcessProvider())
        result=self.drive(engine)
        self.assertEqual(result['status'],'NEEDS_DECISION',result)
        with self.assertRaises(Closed): action(engine.root,'approve','not-the-binding')
        action(engine.root,'approve',result['approval'])
        result=self.drive(Controller(engine.root,reasoning=engine.reasoning))
        self.assertEqual(result['status'],'COMPLETED',result)

    def test_approved_candidate_does_not_merge_after_base_movement(self):
        self.goal=goal(approval=True);engine=self.start(InProcessProvider())
        result=self.drive(engine);action(engine.root,'approve',result['approval'])
        engine.repo.text('update-ref','refs/heads/main',engine.task['head'])
        result=Controller(engine.root).tick()
        self.assertEqual(result['status'],'BLOCKED_POLICY',result)
        self.assertIn('Base moved',result['reason'])

    def test_crash_after_each_recorded_effect_reuses_receipt(self):
        # A hard interruption must bypass ordinary exception diagnostics.
        class Crash(BaseException): pass
        provider=InProcessProvider(); engine=self.start(provider)
        crashed=set()
        def crash(identity):
            kind=engine.state['pending']['kind']
            if kind not in crashed:
                crashed.add(kind);raise Crash(kind)
        engine.store.after_receipt=crash
        for _ in range(100):
            try:
                result=engine.tick()
            except Crash:
                engine=Controller(engine.root,reasoning=provider)
                engine.store.after_receipt=crash
                continue
            if result['status']!='RUNNING': break
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertTrue({'model','commit','verify','negative-control-commit','merge'} <= crashed)
        self.assertEqual(engine.state['model_calls'],len(provider.calls))
        self.assertEqual(len([row for row in provider.calls if row['phase']=='developer']),1)

    def test_indeterminate_model_call_requires_explicit_bounded_retry(self):
        class Crash(BaseException): pass
        class Interrupted:
            def execute(self,_): raise Crash()
        engine=self.start(Interrupted())
        with self.assertRaises(Crash): engine.tick()
        pending=Store(engine.root).state['pending']['id']
        engine=Controller(engine.root,reasoning=InProcessProvider())
        result=engine.tick()
        self.assertEqual(result['status'],'BLOCKED_POLICY')
        self.assertIn('Indeterminate',result['reason'])
        action(engine.root,'retry-effect',pending)
        result=self.drive(Controller(engine.root,reasoning=InProcessProvider()))
        self.assertEqual(result['status'],'COMPLETED',result)

    def test_model_cannot_claim_future_delivery_evidence(self):
        self.goal['items'][0]['acceptance'].append({'id':'AC-2','text':'Merged and verified','kind':'delivery','paths':[],'targets':[]})
        def forgery(payload,result,_):
            if payload['phase']=='reviewer':
                result['acceptance_evidence'][1]['status']='covered'
        engine=self.start(InProcessProvider(forgery)); result=self.drive(engine)
        self.assertEqual(result['status'],'BLOCKED_POLICY',result)
        self.assertNotIn('merge_sha',engine.task)

    def test_context_is_revision_bound_and_retrieval_is_real(self):
        def request(payload,result,_):
            if payload['phase']=='architect' and 'README.md' not in payload['sources']:
                result.update(verdict='need_context',requested_files=['README.md'])
        provider=InProcessProvider(request);engine=self.start(provider)
        result=self.drive(engine)
        self.assertEqual(result['status'],'COMPLETED',result)
        calls=[row for row in provider.calls if row['phase']=='architect']
        self.assertEqual(len(calls),2)
        self.assertIn('Test product',calls[1]['sources']['README.md']['content'])
        self.assertTrue(calls[1]['memory']['entries'])


    def test_replan_retains_frozen_tests_and_uses_distinct_attempt_and_approval(self):
        self.goal=goal(approval=True);provider=InProcessProvider();engine=self.start(provider)
        first=self.drive(engine);original=copy.deepcopy(engine.task['frozen_tests'])
        action(engine.root,'replan')
        engine=Controller(engine.root,reasoning=provider);second=self.drive(engine)
        self.assertEqual(second['status'],'NEEDS_DECISION',second)
        self.assertEqual(engine.task['attempt'],2)
        self.assertEqual(engine.task['frozen_tests'],original)
        self.assertNotEqual(first['approval'],second['approval'])
        self.assertEqual(len([row for row in provider.calls if row['phase']=='tester']),1)
        with self.assertRaises(Closed):action(engine.root,'approve',first['approval'])
        action(engine.root,'approve',second['approval'])
        self.assertEqual(self.drive(Controller(engine.root,reasoning=provider))['status'],'COMPLETED')

    def test_real_candidate_harness_error_preserves_frozen_assertions_and_blocks_repair(self):
        def harness(payload,result,_):
            if payload['phase']=='tester':
                result['edits'][0]['content']=result['edits'][0]['content'].replace(
                    '        self.assertEqual(value(), 2)',
                    '        if value() == 2: raise RuntimeError("harness failure")\n        self.assertEqual(value(), 2)')
        provider=InProcessProvider(harness);engine=self.start(provider)
        result=self.drive(engine)
        self.assertEqual(result['status'],'FAILED',result)
        self.assertIsNotNone(engine.task['frozen_tests'])
        self.assertEqual(len([row for row in provider.calls if row['phase']=='developer']),1)
        self.assertNotIn('merge_sha',engine.task)

    def test_upgrade_requires_paused_unchanged_boundary(self):
        from agent_runtime.actions import upgrade
        provider=InProcessProvider();engine=self.start(provider)
        with self.assertRaises(Exception):upgrade(engine.root)
        action(engine.root,'pause');self.assertTrue(upgrade(engine.root)['paused'])
        action(engine.root,'continue');engine=Controller(engine.root,reasoning=provider)
        self.drive(engine,stop='verify')
        action(engine.root,'pause')
        with self.assertRaises(Exception):upgrade(engine.root,suspend=True)

    def test_budget_exhaustion_cannot_be_reset_by_replan(self):
        self.policy['limits']['model_calls']=1
        provider=InProcessProvider();engine=self.start(provider)
        result=self.drive(engine)
        self.assertEqual(result['status'],'BLOCKED_POLICY',result)
        self.assertEqual(len(provider.calls),1)
        action(engine.root,'replan')
        result=self.drive(Controller(engine.root,reasoning=provider))
        self.assertEqual(result['status'],'BLOCKED_POLICY',result)
        self.assertEqual(len(provider.calls),1)

    def test_owner_cannot_retry_an_approval_or_hard_policy_hold(self):
        self.goal=goal(approval=True);engine=self.start(InProcessProvider());self.drive(engine)
        with self.assertRaises(Closed):action(engine.root,'retry')

    def test_full_cli_runs_without_checkout_on_import_path(self):
        import json,subprocess,sys
        config=self.root/'policy.json';intent=self.root/'goal.json'
        config.write_text(json.dumps(self.policy));intent.write_text(json.dumps(self.goal))
        from runtime_support import ROOT
        result=subprocess.run([sys.executable,'-S','-m','agent_runtime','start','--policy',str(config),
            '--goal',str(intent),'--state',str(self.root/'cli-run'),'--trusted-local'],cwd=self.root,
            env={'PATH':__import__('os').environ['PATH'],'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout[-2000:])
        self.assertEqual(json.loads(result.stdout.splitlines()[-1])['status'],'COMPLETED')


if __name__=='__main__': unittest.main()
