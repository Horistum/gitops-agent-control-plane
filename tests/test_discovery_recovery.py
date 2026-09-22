"""Discovery selection, source retrieval and no-cost diagnosis of held runs."""
import copy
from pathlib import Path
import tempfile
import unittest

from agent_runtime.actions import action, upgrade
from agent_runtime.controller import Controller
from agent_runtime.io import Closed
from agent_runtime.service import RunService
from agent_runtime.store import Store
from runtime_support import build_product, goal, policy, InProcessProvider


class DiscoveryRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.product = self.root / 'product'
        build_product(self.product, two=True)
        self.policy = policy(self.product)
        self.goal = goal(two=True)

    def start(self, transform=None):
        engine = Controller.start(self.root / 'run', self.policy, self.goal, trusted_local=True)
        engine.reasoning = InProcessProvider(transform)
        return engine

    def test_first_call_observes_eligible_item_sources_without_reading_blocked_item(self):
        engine = self.start()
        self.assertEqual(engine.tick()['item'], 'TASK-1')
        payload = engine.reasoning.calls[0]
        self.assertEqual(payload['eligible_items'], ['TASK-1'])
        self.assertEqual(set(payload['sources']), {'app.py'})
        self.assertIn('return 1', payload['sources']['app.py']['content'])

    def test_seed_overflow_is_reported_and_fresh_request_has_priority(self):
        self.goal['items'][1]['dependencies'] = []
        self.goal['items'][0]['context'] = ['app.py', 'README.md']
        self.policy['limits']['context_files'] = 2
        def request(payload, result, turn):
            if turn == 1:
                result.update(verdict='need_context', requested_files=['tools/test.py'])
        engine = self.start(request)
        self.assertEqual(engine.tick()['status'], 'RUNNING')
        first = engine.reasoning.calls[0]
        self.assertEqual(set(first['sources']), {'app.py', 'README.md'})
        self.assertIn('other.py', first['omitted_paths'])
        self.assertEqual(engine.tick()['item'], 'TASK-1')
        second = engine.reasoning.calls[1]
        self.assertIn('tools/test.py', second['sources'])
        self.assertEqual(len(second['sources']), 2)

    def test_refusal_is_visible_in_status_and_decision_and_resume_does_not_repay(self):
        def refuse(payload, result, _):
            result.update(verdict='blocked', selected_item='', summary='The approved interface conflicts with app.py.',
                findings=[{'kind': 'scope', 'severity': 'high', 'description': 'Owner must resolve the interface.'}])
        engine = self.start(refuse)
        report = engine.tick()
        self.assertEqual(report['status'], 'BLOCKED_POLICY')
        self.assertIn('blocked', report['reason'])
        self.assertIn('The approved interface', report['reason'])
        self.assertEqual(report['discovery']['selected_item'], '')
        self.assertEqual(report['discovery']['eligible_items'], ['TASK-1'])
        self.assertTrue(report['recovery']['replan'])
        service = RunService(engine.root)
        decision = service.decision()
        self.assertEqual(decision['reviews']['discovery']['findings'][0]['severity'], 'high')
        self.assertIn('replan', decision['actions'])
        before = (engine.root / 'state.json').read_bytes()
        service.status(); service.decision()
        self.assertEqual(before, (engine.root / 'state.json').read_bytes())
        for _ in range(3):
            self.assertEqual(engine.tick()['status'], 'BLOCKED_POLICY')
        self.assertEqual(len(engine.reasoning.calls), 1)
        self.assertEqual(engine.state['model_calls'], 1)

    def test_ineligible_selection_is_not_replaced_by_an_automatic_fallback(self):
        def ineligible(payload, result, _):
            result['selected_item'] = 'TASK-2'
        engine = self.start(ineligible)
        result = engine.tick()
        self.assertEqual(result['status'], 'BLOCKED_POLICY')
        self.assertIsNone(engine.task)
        self.assertIn('TASK-2', result['reason'])
        self.assertEqual(result['discovery']['selected_item'], 'TASK-2')
        self.assertEqual(engine.state['completed'], [])

    def test_replan_keeps_diagnosis_and_reloads_previously_requested_sources_at_new_head(self):
        def respond(payload, result, turn):
            if turn == 1:
                result.update(verdict='need_context', requested_files=['README.md'], summary='Need the interface notes.')
            elif turn == 2:
                result.update(verdict='blocked', selected_item='', summary='Interface decision needs clarification.')
        engine = self.start(respond)
        engine.tick()
        self.assertEqual(engine.tick()['status'], 'BLOCKED_POLICY')
        old_head = engine.state['discovery']['head']
        response = action(engine.root, 'replan', reason='Recheck updated interface notes')
        self.assertEqual(response['status'], 'RUNNING')
        self.assertIsNone(response['reason'])
        self.assertEqual(response['model_calls'], 2)
        current = engine.repo.context(old_head, ['README.md'], 10000)['README.md']
        new_head = engine.repo.commit(old_head, [{'path': 'README.md', 'expected_sha256': current['sha256'],
            'delete': False, 'content': 'The interface is now clarified.\n'}], 'updated-notes',
            allowed=['README.md'], protected=[])
        engine.repo.text('update-ref', 'refs/heads/main', new_head)
        self.assertEqual(engine.tick()['item'], 'TASK-1')
        retry = engine.reasoning.calls[-1]
        self.assertEqual(retry['task']['head'], new_head)
        self.assertEqual(retry['sources']['README.md']['content'], 'The interface is now clarified.\n')
        self.assertIn('Interface decision needs clarification', str(retry['task']['feedback']))
        self.assertIn(old_head, str(retry['task']['feedback']))
        self.assertEqual(engine.state['model_calls'], 3)
        self.assertEqual(engine.task['context'], ['app.py'])

    def test_exhausted_discovery_cannot_replan_or_reset_budget(self):
        self.policy['limits']['model_calls'] = 1
        def refuse(payload, result, _):
            result.update(verdict='blocked', selected_item='')
        engine = self.start(refuse)
        report = engine.tick()
        self.assertFalse(report['recovery']['replan'])
        self.assertNotIn('replan', RunService(engine.root).decision()['actions'])
        before = (engine.root / 'state.json').read_bytes()
        with self.assertRaisesRegex(Closed, 'budget'):
            action(engine.root, 'replan')
        self.assertEqual(before, (engine.root / 'state.json').read_bytes())

    def test_legacy_diagnosis_and_quiescent_upgrade_preserve_discovery_hints(self):
        def refuse(payload, result, _):
            result.update(verdict='blocked', selected_item='', summary='Legacy model refusal')
        engine = self.start(refuse)
        engine.tick()
        store = Store(engine.root)
        store.state['discovery']['role_results']['discovery'].pop('selected_item', None)
        store.state['discovery'].pop('last_result', None)
        store.save()
        before = copy.deepcopy(store.state)
        report = RunService(engine.root).decision()
        self.assertEqual(report['discovery']['summary'], 'Legacy model refusal')
        self.assertIsNone(report['discovery']['selected_item'])
        self.assertEqual(Store(engine.root).state, before)
        action(engine.root, 'pause')
        upgrade(engine.root)
        self.assertEqual(RunService(engine.root).decision()['previous_discovery']['summary'], 'Legacy model refusal')
        action(engine.root, 'replan', reason='Use corrected discovery prompt')
        action(engine.root, 'continue')
        engine.reasoning = InProcessProvider()
        self.assertEqual(engine.tick()['item'], 'TASK-1')
        self.assertIn('Legacy model refusal', str(engine.reasoning.calls[0]['task']['feedback']))


if __name__ == '__main__':
    unittest.main()
