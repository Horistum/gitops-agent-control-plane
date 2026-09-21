"""Reproductions of the September audit, including installed adapter boundaries."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_runtime.actions import action
from agent_runtime.adapter_check import verify
from agent_runtime.controller import Controller
from agent_runtime.io import Closed, atomic_json
from agent_runtime.registry import registry_status
from agent_runtime.service import RunService
from agent_runtime.store import Store
from runtime_support import build_product, policy, goal, InProcessProvider


class RecoveryCertificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); build_product(self.root / 'product')
        self.policy = policy(self.root / 'product')

    def held_receipt(self, active):
        engine = Controller.start(self.root / 'run', self.policy, goal(), trusted_local=True)
        peer = InProcessProvider(); engine.reasoning = peer
        if active:
            engine.tick(); engine.tick()
        class Crash(BaseException): pass
        engine.store.after_receipt = lambda _: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash): engine.tick()
        pending = Store(engine.root).state['pending']
        path = engine.root / 'receipts' / (pending['id'] + '.json')
        data = path.read_bytes(); path.unlink()
        held = Controller(engine.root, reasoning=peer).tick()
        self.assertEqual(held['status'], 'BLOCKED_POLICY')
        path.write_bytes(data)
        return engine.root, peer, pending, path

    def test_restored_active_receipt_replays_after_owner_reconcile_without_cost(self):
        root, peer, pending, _ = self.held_receipt(True)
        service = RunService(root); document = service.decision()
        before = service.usage(); calls = len(peer.calls)
        with self.assertRaises(Closed): action(root, 'retry-effect', pending['id'])
        service.act('reconcile-effect', document['decision_hash'], binding=pending['id'], reason='restored original evidence')
        with patch('agent_runtime.reasoning.Reasoning.prepare', side_effect=AssertionError('must not prepare')):
            resumed = Controller(root, reasoning=peer).tick()
        self.assertEqual(resumed['status'], 'RUNNING')
        self.assertNotEqual(resumed['phase'], 'await_human')
        self.assertEqual(len(peer.calls), calls)
        self.assertEqual(service.usage()['reserved_calls'], before['reserved_calls'])
        self.assertEqual(service.usage()['recorded_calls'], before['recorded_calls'])
        with self.assertRaises(Closed): service.act('reconcile-effect', document['decision_hash'], binding=pending['id'])

    def test_restored_discovery_receipt_replays_after_restart(self):
        root, peer, pending, _ = self.held_receipt(False)
        from agent_runtime.cli import main
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['reconcile-effect', '--state', str(root), '--binding', pending['id']]), 0)
        self.assertEqual(Controller(root, reasoning=peer).tick()['phase'], 'baseline')
        self.assertEqual(len(peer.calls), 1)
        self.assertEqual(RunService(root).usage()['reserved_calls'], 1)

    def test_reconcile_rejects_wrong_identity_missing_tampered_receipt_and_changed_frame(self):
        root, _, pending, path = self.held_receipt(True)
        with self.assertRaises(Closed): action(root, 'reconcile-effect', 'f' * 64)
        data = path.read_bytes(); path.unlink()
        with self.assertRaises(Closed): action(root, 'reconcile-effect', pending['id'])
        path.write_bytes(data)
        receipt = json.loads(data); receipt['output']['usage'] = {'input_tokens': 99}
        atomic_json(path, receipt)
        with self.assertRaises(Closed): action(root, 'reconcile-effect', pending['id'])
        path.write_bytes(data)
        store = Store(root); store.state['task']['head'] = 'e' * 40; store.save()
        with self.assertRaisesRegex(Closed, 'frame changed'): action(root, 'reconcile-effect', pending['id'])

    def test_registry_isolates_null_list_bad_task_and_missing_state(self):
        runs = self.root / 'runs'
        good = Controller.start(runs / 'good', self.policy, goal(), trusted_local=True)
        bad = Controller.start(runs / 'bad', self.policy, goal(), trusted_local=True)
        original = copy.deepcopy(bad.state)
        for value in (None, [], {**original, 'task': ['invalid']}, {**original, 'archive': [None]}):
            atomic_json(bad.root / 'state.json', value)
            rows = registry_status(runs)['runs']
            self.assertEqual([(Path(r['root']).name, r['readable']) for r in rows], [('bad', False), ('good', True)])
        (bad.root / 'state.json').unlink()
        self.assertFalse(registry_status(runs)['runs'][0]['readable'])
        with self.assertRaises(Closed): registry_status(good.root, limit=0)

    def test_certification_requires_handshake_before_any_live_attempt(self):
        with patch('agent_runtime.reasoning.Reasoning.execute') as execute:
            result = verify(self.policy, live=True, phases=['discovery'])
        self.assertFalse(result['passed']); execute.assert_not_called()
        self.assertEqual(result['readiness']['checks']['adapter'], 'not_checked')

    def adapter_policy(self, *, fail=False):
        import agent_runtime
        installed = str(Path(agent_runtime.__file__).resolve().parents[1])
        shim = self.root / 'adapter.py'
        shim.write_text('import sys,io,json\nsys.path.insert(0,' + repr(installed) + ')\n'
            'from agent_runtime import openai_adapter as adapter\n'
            'class Opener:\n'
            ' def open(self,req,timeout):\n'
            '  assert len(req.get_header("X-client-request-id")) == 64\n'
            '  value={"verdict":"ready","summary":"fixture","risk":"low","requested_files":[],"requested_searches":[],"requested_facts":[],"findings":[],"acceptance_evidence":[],"selected_item":"SELF-CERT-001"}\n'
            '  return io.BytesIO(json.dumps({"id":"fixture","choices":[{"finish_reason":"stop","message":{"content":json.dumps(value)}}],"usage":{"prompt_tokens":12,"completion_tokens":3}}).encode())\n'
            'adapter.request.build_opener=lambda *args: Opener()\n'
            + ('if "--check" not in sys.argv: sys.exit(2)\n' if fail else '')
            + 'sys.exit(adapter.main())\n')
        config = copy.deepcopy(self.policy)
        config['reasoning'].update(argv=[sys.executable, str(shim)],
            check_argv=[sys.executable, str(shim), '--check'], protocol=2, model='fixture',
            credentials={'OPENAI_API_KEY': {'kind':'env','name':'SYNTHETIC_ADAPTER_KEY'}})
        return config

    def test_certification_drives_bundled_adapter_with_identity_and_no_real_http(self):
        config = self.adapter_policy()
        with patch.dict(os.environ, {'SYNTHETIC_ADAPTER_KEY':'fixture'}):
            result = verify(config, live=True, phases=['discovery', 'discovery'])
        self.assertTrue(result['passed'], result)
        self.assertEqual(len(result['phases']), 1)
        self.assertEqual(result['phases']['discovery']['usage'], {'input_tokens':12,'output_tokens':3})
        self.assertEqual(len(result['phases']['discovery']['effect_id']), 64)

    def test_certification_failure_is_structured_and_stops_further_paid_probes(self):
        with patch.dict(os.environ, {'SYNTHETIC_ADAPTER_KEY':'fixture'}):
            result = verify(self.adapter_policy(fail=True), live=True, phases=['discovery', 'architect'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['phases']['discovery']['outcome'], 'unknown')
        self.assertEqual(result['not_attempted'], ['architect'])
