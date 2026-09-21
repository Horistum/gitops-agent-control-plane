import copy
from http.client import HTTPConnection
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError
from zipfile import ZipFile

from agent_runtime.actions import action
from agent_runtime.backup import backup, restore
from agent_runtime.controller import Controller
from agent_runtime.doctor import diagnose
from agent_runtime.io import Closed, canonical, locked, read_json
from agent_runtime.openai_adapter import complete, endpoint
from agent_runtime.review import create_server
from agent_runtime.service import RunService
from agent_runtime.supervisor import supervise
from runtime_support import ROOT, build_product, goal, policy, proposal


class OwnerOperationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.product = self.root / 'product'
        build_product(self.product); self.config = policy(self.product)

    def start(self):
        return Controller.start(self.root / 'run', self.config, goal(), trusted_local=True)

    def test_doctor_reports_missing_credentials_and_unchecked_adapter(self):
        self.config['reasoning']['credentials'] = {'OPENAI_API_KEY': {'kind': 'env', 'name': 'ABSENT_AUDIT_KEY'}}
        with patch.dict(os.environ):
            os.environ.pop('ABSENT_AUDIT_KEY', None)
            report = diagnose(self.config, goal())
        self.assertFalse(report['ready']); self.assertEqual(report['checks']['reasoning'], 'failed')
        self.config['reasoning'].pop('credentials')
        report = diagnose(self.config, goal())
        self.assertFalse(report['ready']); self.assertEqual(report['checks']['reasoning'], 'not_checked')

    def test_real_adapter_handshake_performs_no_http_request(self):
        import agent_runtime
        installed_root = Path(agent_runtime.__file__).resolve().parents[1]
        self.config['reasoning'].update(protocol=2, model='operator-model',
            check_argv=[sys.executable, '-c', f'import sys;sys.path.insert(0,{str(installed_root)!r});from agent_runtime.openai_adapter import main;sys.exit(main(["--check"]))'],
            credentials={'OPENAI_API_KEY': {'kind': 'env', 'name': 'LOCAL_ADAPTER_KEY'}})
        with patch.dict(os.environ, {'LOCAL_ADAPTER_KEY': 'synthetic-value'}):
            report = diagnose(self.config, goal())
        self.assertTrue(report['ready'], report)
        self.assertFalse(report['model_called']); self.assertEqual(report['checks']['live_model'], 'not_checked')
        self.assertEqual(report['reasoning']['authentication'], 'not-checked')

    def test_http_adapter_maps_usage_and_never_retries_transport_failure(self):
        payload = {'phase': 'discovery', 'task': {}, 'eligible_items': ['TASK-1']}
        envelope = {'schema': 'command-reasoning/v2', 'model': 'operator-model', 'effect_id': 'a'*64,
                    'input': payload, 'instructions': 'Return JSON', 'output_schema': {'type':'object'}}
        body = {'id': 'request-1', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(proposal(payload))}}],
                'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'prompt_tokens_details': {'cached_tokens': 4}}}
        class Response(io.BytesIO):
            pass
        class Opener:
            calls = 0
            def open(self, req, timeout):
                self.calls += 1; self.request = req
                return Response(canonical(body))
        opener = Opener()
        result = complete(envelope, url='https://api.openai.com/v1/chat/completions', key='synthetic',
                          timeout=10, max_tokens=64, opener=opener)
        self.assertEqual(result['usage'], {'input_tokens':12, 'output_tokens':3, 'cached_input_tokens':4})
        sent = json.loads(opener.request.data)
        self.assertEqual(sent['n'], 1); self.assertFalse(sent['stream']); self.assertNotIn('tools', sent)
        body['choices'][0]['finish_reason'] = 'length'
        result = complete(envelope, url='https://api.openai.com/v1/chat/completions', key='synthetic',
                          timeout=10, max_tokens=64, opener=opener)
        self.assertEqual(result['result'], {}); self.assertEqual(result['usage']['output_tokens'], 3)
        with patch.object(opener, 'open', side_effect=URLError('timeout')) as send:
            with self.assertRaises(URLError):
                complete(envelope, url='https://api.openai.com/v1/chat/completions', key='synthetic',
                         timeout=10, max_tokens=64, opener=opener)
            self.assertEqual(send.call_count, 1)
        for url in ('http://example.com', 'https://token@example.com', 'https://example.com?secret=x'):
            with self.assertRaises(Closed): endpoint(url)

    def test_supervisor_runs_ready_phases_immediately_and_backs_off_waits(self):
        class Service:
            sequence = ['RUNNING', 'WAITING_EXTERNAL', 'WAITING_EXTERNAL', 'RUNNING', 'COMPLETED']
            index = 0
            def status(self): return {'status': self.sequence[min(self.index, 4)], 'paused': False}
            def tick(self):
                state = self.status(); self.index += 1
                return {'outcome':'observed', 'state':state}
        delays = []
        result = supervise(self.root/'run', service=Service(), wait=delays.append, poll_seconds=2, max_backoff=8)
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(delays, [2, 4])
        self.assertEqual(read_json(self.root/'run/health.json')['state'], 'finished')

    def test_backup_roundtrip_resumes_without_repeating_recorded_discovery(self):
        engine = self.start(); engine.tick(); action(engine.root, 'pause')
        destination = self.root/'run-backup.zip'
        backup(engine.root, destination)
        restored = self.root/'restored'
        self.assertTrue(restore(destination, restored)['paused'])
        self.assertEqual(RunService(restored).usage()['recorded_calls'], 1)
        action(restored, 'continue'); engine = Controller(restored)
        before = engine.state['model_calls']; engine.tick()
        self.assertEqual(engine.state['model_calls'], before)  # baseline, not another discovery
        with self.assertRaises(Closed): restore(destination, restored)

    def test_backup_rejects_live_run_and_restore_rejects_tampering(self):
        engine = self.start()
        with self.assertRaises(Closed): backup(engine.root, self.root/'live.zip')
        action(engine.root, 'pause'); backup(engine.root, self.root/'good.zip')
        with ZipFile(self.root/'good.zip') as source, ZipFile(self.root/'bad.zip', 'w') as target:
            for name in source.namelist():
                target.writestr(name, b'{}' if name == 'state.json' else source.read(name))
        with self.assertRaisesRegex(Closed, 'checksum'): restore(self.root/'bad.zip', self.root/'restore')
        self.assertFalse((self.root/'restore').exists())

    def test_http_monitoring_reads_while_writer_active_and_actions_reject_stale_state(self):
        engine = self.start(); token = 's'*40
        server = create_server(engine.root, token, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        def request(method, path, data=None):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            connection.request(method, path, body=json.dumps(data) if data else None,
                headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'})
            response = connection.getresponse(); result = (response.status, json.loads(response.read())); connection.close()
            return result
        with locked(engine.root):
            self.assertEqual(request('GET', '/api/status')[0], 200)
            self.assertEqual(request('GET', '/api/usage')[0], 200)
            status, document = request('GET', '/api/decision')
        body = {'action':'pause', 'decision_hash':document['decision_hash'], 'binding':None,
                'reason':'maintenance', 'accept_duplicate_cost':False}
        self.assertEqual(request('POST', '/api/action', body)[0], 200)
        body['action'] = 'cancel'
        self.assertEqual(request('POST', '/api/action', body)[0], 409)
        self.assertEqual(RunService(engine.root).decision()['recent_actions'][-1]['reason'], 'maintenance')
