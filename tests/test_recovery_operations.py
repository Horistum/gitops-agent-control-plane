"""Crash boundaries, real provider processes and concurrent observation."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_runtime.actions import action
from agent_runtime.controller import Controller
from agent_runtime.io import Closed, Unavailable, NotDispatched, locked
from agent_runtime.service import RunService
from agent_runtime.store import Store
from runtime_support import build_product, goal, policy, InProcessProvider


class RecoveryOperationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.product = self.root / 'product'
        build_product(self.product); self.config = policy(self.product)

    def start(self, approval=False):
        return Controller.start(self.root / 'run', self.config, goal(approval=approval), trusted_local=True)

    def test_missing_credential_and_broker_outage_do_not_dispatch_or_reserve(self):
        engine = self.start()
        for failure in (Closed('missing'), Unavailable('broker outage')):
            with patch('agent_runtime.credentials.CredentialResolver.provider_environment', side_effect=failure), \
                    patch('agent_runtime.reasoning.run') as provider:
                result = engine.tick()
            self.assertEqual(result['status'], 'WAITING_EXTERNAL')
            self.assertEqual(result['model_calls'], 0)
            self.assertIsNone(result['pending_effect']); provider.assert_not_called()
        self.assertEqual(engine.tick()['status'], 'RUNNING')
        self.assertEqual(engine.state['model_calls'], 1)

    def test_spawn_failure_is_proven_not_dispatched_but_timeout_is_unknown(self):
        engine = self.start()
        with patch('agent_runtime.reasoning.run', side_effect=NotDispatched('spawn failed')):
            self.assertEqual(engine.tick()['model_calls'], 0)
        with patch('agent_runtime.reasoning.run', side_effect=Unavailable('timeout')) as provider:
            engine.tick()
            for _ in range(3):
                Controller(engine.root).tick()
            self.assertEqual(provider.call_count, 1)
        report = RunService(engine.root).usage()
        self.assertEqual((report['reserved_calls'], report['unknown_outcomes']), (1, 1))

    def test_interrupted_first_state_write_recovers_start_and_resume(self):
        with patch.object(Store, 'save', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): self.start()
        self.assertTrue((self.root / 'run/product.git').is_dir())
        self.assertFalse((self.root / 'run/state.json').exists())
        engine = Controller.resume(self.root / 'run')
        self.assertEqual(engine.tick()['status'], 'RUNNING')
        with self.assertRaisesRegex(Closed, 'Existing run'): self.start()

    def test_interrupted_clone_is_confined_and_authority_change_is_rejected(self):
        from agent_runtime.git import GitRepository
        initialize = GitRepository.initialize
        with patch.object(GitRepository, 'initialize', side_effect=OSError('clone interrupted')):
            with self.assertRaises(OSError): self.start()
        self.config['limits']['model_calls'] -= 1
        with self.assertRaisesRegex(Closed, 'authority'): self.start()
        self.config['limits']['model_calls'] += 1
        with patch.object(GitRepository, 'initialize', wraps=initialize):
            self.assertEqual(self.start().tick()['status'], 'RUNNING')

    def test_duplicate_keys_and_nonfinite_provider_output_are_recorded_errors(self):
        for body in ('{bad', '{"verdict":"ready","verdict":"ready"}', '{"x":NaN}'):
            with self.subTest(body=body):
                self.config['reasoning']['argv'] = [sys.executable, '-c', 'print(' + repr(body) + ')']
                root = self.root / str(len(list(self.root.iterdir())))
                engine = Controller.start(root, self.config, goal(), trusted_local=True)
                self.assertEqual(engine.tick()['status'], 'RUNNING')
                report = RunService(root).usage()
                self.assertEqual((report['protocol_errors'], report['unknown_outcomes']), (1, 0))

    def test_receipt_replay_never_prepares_or_dispatches_again(self):
        engine = self.start()
        class Crash(BaseException): pass
        engine.store.after_receipt = lambda _: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash): engine.tick()
        with patch('agent_runtime.reasoning.Reasoning.prepare', side_effect=AssertionError('prepare during replay')), \
                patch('agent_runtime.reasoning.run', side_effect=AssertionError('duplicate provider call')):
            self.assertEqual(Controller(engine.root).tick()['status'], 'RUNNING')
        self.assertEqual(RunService(engine.root).usage()['reserved_calls'], 1)

    def test_observation_during_writer_and_after_exact_approval(self):
        engine = self.start(approval=True); service = RunService(engine.root)
        for _ in range(100):
            if engine.tick()['status'] != 'RUNNING': break
        before = service.decision()
        with locked(engine.root):
            self.assertEqual(service.status()['status'], 'NEEDS_DECISION')
            self.assertEqual(service.decision(), before)
            self.assertGreater(service.usage()['recorded_calls'], 0)
        result = service.approve(before['binding'], before['decision_hash'])
        self.assertEqual(result['phase'], 'merge')
        self.assertEqual(service.status()['phase'], service.decision()['phase'])
        with self.assertRaisesRegex(Closed, 'changed'):
            service.act('cancel', before['decision_hash'])
        self.assertEqual(service.decision()['recent_actions'][-1]['action'], 'approve')

    def test_usage_ignores_receipts_outside_its_atomic_snapshot(self):
        engine = self.start(); older = Store(engine.root)
        engine.tick()
        from agent_runtime.usage import usage_report
        self.assertEqual(usage_report(older)['reserved_calls'], 0)
        current = RunService(engine.root).usage()
        self.assertEqual((current['reserved_calls'], current['recorded_calls']), (1, 1))
