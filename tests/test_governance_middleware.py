"""Real provider processes, receipt crash boundaries and authenticated local HTTP."""
import copy
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from control_plane_core import fingerprint
from agent_runtime.actions import action
from agent_runtime.contracts import validate_configuration
from agent_runtime.controller import Controller
from agent_runtime.credentials import CredentialResolver
from agent_runtime.github import GitHub
from agent_runtime.io import Closed, atomic_json, locked, read_json
from agent_runtime.reasoning import Reasoning
from agent_runtime.review import create_server
from agent_runtime.service import RunService
from agent_runtime.store import Store
from agent_runtime.usage import usage_report, validate_usage
from runtime_support import ROOT, InProcessProvider, build_product, goal, policy


class MiddlewareTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.product = self.root / 'product'
        build_product(self.product)
        self.policy = policy(self.product)
        self.goal = goal()

    def script(self, name, source):
        path = self.root / name
        path.write_text(source)
        return [sys.executable, str(path)]

    def start(self, approval=False):
        engine = Controller.start(self.root / 'run', self.policy, goal(approval=approval), trusted_local=True)
        return engine

    def hold(self):
        engine = self.start(approval=True)
        for _ in range(100):
            result = engine.tick()
            if result['status'] != 'RUNNING':
                break
        self.assertEqual(result['status'], 'NEEDS_DECISION', result)
        return engine, RunService(engine.root)

    def test_v2_real_provider_credentials_usage_and_complete_goal(self):
        argv = self.script('provider.py',
            'import json,os,sys\n'
            f'sys.path.insert(0,{str(ROOT / "tests")!r})\n'
            'from runtime_support import proposal\n'
            'request=json.load(sys.stdin)\n'
            'assert request["schema"]=="command-reasoning/v2"\n'
            'assert len(request["effect_id"])==64\n'
            'assert request["model"]=="operator-model"\n'
            'assert os.environ["MODEL_API_KEY"]=="model-secret"\n'
            'assert "GH_TOKEN" not in os.environ and "SSH_AUTH_SOCK" not in os.environ\n'
            'assert "model-secret" not in json.dumps(request)\n'
            'print(json.dumps({"schema":"command-reasoning/v2","result":proposal(request["input"]),'
            '"usage":{"input_tokens":10,"output_tokens":3,"cached_input_tokens":2},'
            '"provider":{"id":"test-peer","model":"operator-model","request_id":request["effect_id"]}}))\n')
        self.policy['reasoning'].update(argv=argv, protocol=2, model='operator-model',
            credentials={'MODEL_API_KEY': {'kind': 'env', 'name': 'TENANT_MODEL_KEY'}})
        with patch.dict(os.environ, {'TENANT_MODEL_KEY': 'model-secret', 'GH_TOKEN': 'gh-secret'}):
            engine = self.start()
            service = RunService(engine.root)
            for _ in range(100):
                outcome = service.tick()
                if outcome['state']['status'] != 'RUNNING':
                    break
        self.assertEqual(outcome['state']['status'], 'COMPLETED', outcome)
        report = service.usage()
        self.assertGreater(report['recorded_calls'], 5)
        self.assertEqual(report['reserved_calls'], report['recorded_calls'])
        self.assertEqual(report['reported_tokens']['input_tokens'], 10 * report['recorded_calls'])
        self.assertEqual(report['unknown_outcomes'], 0)
        self.assertFalse(report['billing_ready'])
        self.assertEqual(len({row['effect_id'] for row in report['calls']}), report['recorded_calls'])
        for path in engine.root.rglob('*.json'):
            self.assertNotIn('model-secret', path.read_text())
            self.assertNotIn('gh-secret', path.read_text())

    def test_broker_rotates_and_does_not_inherit_controller_secrets(self):
        current = self.root / 'current'
        current.write_text('first-token')
        argv = self.script('broker.py',
            'import json,os,sys\nfrom pathlib import Path\n'
            'r=json.load(sys.stdin)\nassert r=={"schema":1,"reference":"tenant-A/github","purpose":"github:o/r"}\n'
            'assert "GH_TOKEN" not in os.environ and "SSH_AUTH_SOCK" not in os.environ\n'
            f'print(json.dumps({{"value":Path({str(current)!r}).read_text()}}))\n')
        reference = {'kind': 'command', 'argv': argv, 'reference': 'tenant-A/github', 'timeout': 5}
        resolver = CredentialResolver()
        with patch.dict(os.environ, {'GH_TOKEN': 'must-not-leak', 'SSH_AUTH_SOCK': 'must-not-leak'}):
            self.assertEqual(resolver.resolve(reference, purpose='github:o/r'), 'first-token')
            current.write_text('rotated-token')
            self.assertEqual(resolver.resolve(reference, purpose='github:o/r'), 'rotated-token')

    def test_broker_error_does_not_disclose_response_or_stderr(self):
        reference = {'kind': 'command', 'argv': self.script('bad.py',
            'import sys\nprint("secret-output")\nprint("secret-stderr",file=sys.stderr)\n'),
            'reference': 'tenant-A/key', 'timeout': 5}
        with self.assertRaises(Closed) as caught:
            CredentialResolver().resolve(reference, purpose='test')
        self.assertNotIn('secret', str(caught.exception))

    def test_credential_policy_blocks_ambient_environment_overrides(self):
        for name in ('PATH', 'HOME', 'PYTHONPATH', 'LD_PRELOAD', 'GH_TOKEN', 'SSH_AUTH_SOCK', 'CODEX_HOME', 'HTTPS_PROXY',
                     'GCONV_PATH', 'OPENSSL_CONF', 'NODE_PATH', 'PERL5LIB'):
            with self.subTest(name=name):
                config = copy.deepcopy(self.policy)
                config['reasoning']['credentials'] = {name: {'kind': 'env', 'name': 'SECRET'}}
                with self.assertRaises(Closed):
                    validate_configuration(config, self.goal)
        config = copy.deepcopy(self.policy)
        config['publication'].update(kind='github', repository='o/r',
            required_checks=[{'name': 'ci', 'app_id': 1}], credential={'kind': 'env', 'name': 'SECRET'})
        with self.assertRaisesRegex(Closed, 'one GitHub credential'):
            validate_configuration(config, self.goal)

    def test_github_resolves_rotating_credential_for_every_api_request(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, _): return b'{}'
        class Opener:
            def __init__(self): self.headers = []
            def open(self, req, **_):
                self.headers.append(req.get_header('Authorization'))
                return Response()
        config = {'repository': 'o/r', 'token_env': '', 'credential': {'kind': 'env', 'name': 'ROTATING_TOKEN'}}
        api = GitHub(config, 'main')
        api.opener = Opener()
        for token in ('old', 'new'):
            with patch.dict(os.environ, {'ROTATING_TOKEN': token}):
                api.api('/repos/o/r')
        self.assertEqual(api.opener.headers, ['Bearer old', 'Bearer new'])

    def test_protocol_error_preserves_valid_reported_usage_without_raw_output(self):
        response = {'schema': 'command-reasoning/v2', 'result': {'verdict': 'secret-invalid'},
            'usage': {'input_tokens': 7}, 'provider': {'id': 'peer', 'model': 'm', 'request_id': 'r'}}
        config = {**self.policy['reasoning'], 'protocol': 2,
                  'argv': self.script('invalid.py', 'print(' + repr(json.dumps(response)) + ')\n')}
        result = Reasoning(config).execute({'phase': 'discovery'})
        self.assertIn('protocol_error', result)
        self.assertEqual(result['usage'], {'input_tokens': 7})
        self.assertNotIn('secret-invalid', json.dumps(result))

    def test_invalid_usage_does_not_turn_into_zero_cost_success(self):
        for usage in ({'input_tokens': True}, {'output_tokens': -1}, {'input_tokens': 1.5},
                      {'cached_input_tokens': 2}, {'input_tokens': 1, 'cached_input_tokens': 2}, {'cost': 5}):
            with self.subTest(usage=usage), self.assertRaises(Closed):
                validate_usage(usage)

    def test_recorded_crash_is_accounted_once_and_replayed_without_call(self):
        # Simulate process termination, outside the diagnostic Exception boundary.
        class Crash(BaseException): pass
        engine = self.start()
        provider = InProcessProvider()
        engine.reasoning = provider
        engine.store.after_receipt = lambda _: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash): engine.tick()
        service = RunService(engine.root)
        self.assertEqual(service.usage()['recorded_calls'], 1)
        self.assertEqual(service.usage()['unknown_outcomes'], 0)
        Controller(engine.root, reasoning=provider).tick()
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(service.usage()['reserved_calls'], 1)

    def test_unknown_outcome_and_explicit_retry_remain_separate_reservations(self):
        class Interrupted:
            def execute(self, _): raise RuntimeError('crash before receipt')
        engine = self.start()
        engine.reasoning = Interrupted()
        failure = engine.tick()
        self.assertEqual(failure['status'], 'BLOCKED_POLICY')
        self.assertEqual(failure['diagnostic']['code'], 'UNEXPECTED_ERROR')
        service = RunService(engine.root)
        report = service.usage()
        self.assertEqual((report['reserved_calls'], report['recorded_calls'], report['unknown_outcomes']), (1, 0, 1))
        action(engine.root, 'retry-effect', report['uncertain_calls'][0]['effect_id'])
        Controller(engine.root).tick()
        report = service.usage()
        self.assertEqual((report['reserved_calls'], report['recorded_calls'], report['unknown_outcomes']), (2, 1, 1))
        self.assertTrue(report['uncertain_calls'][0]['abandoned'])

    def test_receipt_tampering_and_deletion_fail_accounting(self):
        engine = self.start()
        engine.tick()
        path = next((engine.root / 'receipts').glob('*.json'))
        value = read_json(path)
        value['output']['usage'] = {'input_tokens': 9000}
        atomic_json(path, value)
        with self.assertRaises(Closed): RunService(engine.root).usage()
        path.unlink()
        with self.assertRaises(Closed): RunService(engine.root).usage()

    def test_receipt_replay_cannot_cross_an_unrelated_pending_effect(self):
        engine = self.start()
        engine.tick()
        store = Store(engine.root)
        path = next((engine.root / 'receipts').glob('*.json'))
        receipt = read_json(path)
        store.state['task'] = None
        store.state['pending'] = {'id': 'a' * 64, 'kind': 'model'}
        with self.assertRaisesRegex(Closed, 'different effect'):
            store.effect('model', receipt['request']['payload'], lambda _: self.fail('must not execute'))

    def test_worker_contention_is_retryable_and_consumes_no_budget(self):
        engine = self.start()
        with locked(engine.root):
            self.assertEqual(RunService(engine.root).tick(), {'outcome': 'busy', 'retryable': True})
        self.assertEqual(Store(engine.root).state['model_calls'], 0)

    def test_approval_recomputes_identity_and_rejects_stale_display(self):
        engine, service = self.hold()
        shown = service.decision()
        self.assertTrue(shown['approvable'])
        self.assertIn('findings', shown['reviews']['reviewer'])
        store = Store(engine.root)
        store.state['task']['role_results']['reviewer']['findings'].append(
            {'kind': 'scope', 'severity': 'low', 'description': 'new review note'})
        store.save()
        with self.assertRaisesRegex(Closed, 'Displayed decision changed'):
            service.approve(shown['binding'], shown['decision_hash'])
        store.state['task']['head'] = 'a' * 40
        store.save()
        self.assertFalse(service.decision()['approvable'])
        with self.assertRaisesRegex(Closed, 'exact current'):
            action(engine.root, 'approve', shown['binding'])

    def test_decision_projection_is_a_copy_and_hashes_exact_display(self):
        engine, service = self.hold()
        value = service.decision()
        checksum = value.pop('decision_hash')
        self.assertEqual(checksum, fingerprint(value))
        value['reviews'].clear()
        self.assertTrue(service.decision()['reviews'])

    def test_review_http_auth_origin_host_snapshot_and_approval(self):
        engine, service = self.hold()
        token = 'owner-review-test-token-' + 'x' * 32
        server = create_server(engine.root, token, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=2)))
        def request(method, path, body=None, **headers):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                return response.status, response.read(), dict(response.getheaders())
            finally:
                connection.close()
        self.assertEqual(request('GET', '/api/decision')[0], 401)
        headers = {'Authorization': 'Bearer ' + token}
        self.assertEqual(request('GET', '/api/decision', **headers, Origin='https://evil.example')[0], 403)
        self.assertEqual(request('GET', '/api/decision', **headers, Host='evil.example')[0], 403)
        status, body, received = request('GET', '/api/decision', **headers)
        self.assertEqual(status, 200)
        shown = json.loads(body)
        self.assertEqual(shown, service.decision())
        self.assertEqual(received['Cache-Control'], 'no-store')
        page = request('GET', '/')[1]
        self.assertNotIn(token.encode(), page)
        self.assertIn(b'type="password"', page)
        script = request('GET', '/app.js')[1]
        self.assertIn(b'textContent', script)
        self.assertNotIn(b'innerHTML', script)
        data = json.dumps({'binding': shown['binding'], 'decision_hash': shown['decision_hash']})
        self.assertEqual(request('POST', '/api/approve', data, **headers)[0], 400)
        headers['Content-Type'] = 'application/json'
        self.assertEqual(request('POST', '/api/approve', data, **headers, Origin='https://evil.example')[0], 403)
        self.assertEqual(request('POST', '/api/approve', data, **headers)[0], 200)
        self.assertEqual(request('POST', '/api/approve', data, **headers)[0], 409)
        self.assertEqual(Store(engine.root).state['human_actions'][-1]['decision_hash'], shown['decision_hash'])

    def test_json_reader_rejects_nonregular_file_without_blocking(self):
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaises(Closed): read_json(fifo)


if __name__ == '__main__':
    unittest.main()
