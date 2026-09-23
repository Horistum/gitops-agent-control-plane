"""Recovery after executable drift and actionable failures across real surfaces."""
import contextlib
import copy
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from agent_runtime.actions import action, upgrade
from agent_runtime.cli import main
from agent_runtime.controller import Controller
from agent_runtime.diagnostics import LOG_NAME, provider_error, recent_events
from agent_runtime.doctor import diagnose
from agent_runtime.io import Busy, Closed, Unavailable, locked
from agent_runtime.review import create_server
from agent_runtime.service import RunService
from agent_runtime.store import Store
from runtime_support import InProcessProvider, build_product, goal, policy


class RuntimeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        build_product(self.root / 'product')
        self.policy = policy(self.root / 'product')

    def start(self):
        return Controller.start(self.root / 'run', self.policy, goal(), trusted_local=True)

    @contextlib.contextmanager
    def changed_runtime(self):
        with contextlib.ExitStack() as stack:
            for module in ('store', 'controller', 'actions'):
                stack.enter_context(patch(f'agent_runtime.{module}.runtime_fingerprint', return_value='f' * 64))
            yield

    def server(self, root):
        token = 'private-review-token-' + 'x' * 40
        server = create_server(root, token, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=2)))

        def request(method, path, body=None, *, authenticated=True):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'Content-Type': 'application/json'}
            if authenticated:
                headers['Authorization'] = 'Bearer ' + token
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse(); raw = response.read(); status = response.status
            connection.close()
            return status, json.loads(raw)

        return request, token

    def test_changed_runtime_can_pause_and_upgrade_without_resetting_authority_or_budget(self):
        engine = self.start(); service = RunService(engine.root)
        original = copy.deepcopy(engine.state)
        with self.changed_runtime():
            before = (engine.root / 'state.json').read_bytes()
            shown = service.decision()
            self.assertEqual(shown['diagnostic']['code'], 'RUNTIME_CHANGED')
            self.assertEqual(shown['actions'], ['pause'])
            self.assertEqual(service.decision(), shown)
            self.assertEqual((engine.root / 'state.json').read_bytes(), before)
            self.assertFalse((engine.root / LOG_NAME).exists())
            with self.assertRaisesRegex(Closed, 'Runtime changed'):
                action(engine.root, 'continue')
            with patch('agent_runtime.actions.Controller', side_effect=AssertionError('pause constructed controller')):
                result = service.act('pause', shown['decision_hash'], reason='upgrade recovery')
            self.assertTrue(result['paused'])
            paused = Store(engine.root).state
            for field in ('policy_hash', 'runtime_hash', 'effect_epoch', 'model_calls', 'pending'):
                self.assertEqual(paused[field], original[field])
            self.assertEqual(paused['human_actions'][-1]['reason'], 'upgrade recovery')
            self.assertEqual(service.decision()['actions'], [])
            self.assertTrue(upgrade(engine.root)['upgraded'])
            action(engine.root, 'continue')
            recovered = Controller(engine.root, reasoning=InProcessProvider()).tick()
            self.assertEqual(recovered['status'], 'RUNNING')
            self.assertEqual(recovered['item'], 'TASK-1')
            self.assertEqual(recovered['model_calls'], 1)

    def test_drift_pause_preserves_unknown_effect_and_upgrade_still_refuses_it(self):
        engine = self.start()
        with patch('agent_runtime.reasoning.run', side_effect=Unavailable('connection lost')):
            engine.tick()
        before = copy.deepcopy(Store(engine.root).state)
        self.assertIsNotNone(before['pending'])
        with self.changed_runtime():
            action(engine.root, 'pause')
            after = Store(engine.root).state
            for field in ('pending', 'runtime_hash', 'effect_epoch', 'model_calls', 'receipts'):
                self.assertEqual(after.get(field), before.get(field))
            with self.assertRaisesRegex(Closed, 'pending effect'):
                upgrade(engine.root)

    def test_pause_keeps_writer_lock_stale_decision_and_authority_guards(self):
        engine = self.start(); service = RunService(engine.root)
        with self.changed_runtime():
            shown = service.decision()
            with locked(engine.root), self.assertRaises(Busy):
                action(engine.root, 'pause')
            action(engine.root, 'pause')
            with self.assertRaisesRegex(Closed, 'Displayed decision changed'):
                service.act('pause', shown['decision_hash'])
            store = Store(engine.root)
            store.state['policy']['limits']['model_calls'] += 1; store.save()
            with self.assertRaisesRegex(Closed, 'authority snapshot'):
                action(engine.root, 'pause')
            with self.assertRaisesRegex(Closed, 'authority snapshot'):
                upgrade(engine.root)

    def test_unknown_exception_keeps_cause_location_and_pending_without_redispatch(self):
        engine = self.start()
        secret = 'never-persist-this-credential-12345'
        def fail(*_):
            private_local = 'local-variable-must-not-appear'
            try:
                raise LookupError('adapter lookup failed')
            except LookupError as cause:
                raise RuntimeError('unclassified adapter failure: ' + secret) from cause
        peer = InProcessProvider(fail); engine.reasoning = peer
        with patch.dict(os.environ, {'CUSTOM_API_KEY': secret}):
            result = engine.tick()
            document = RunService(engine.root).decision()
            diagnostic = document['diagnostic']
            self.assertEqual(result['status'], 'BLOCKED_POLICY')
            self.assertEqual(diagnostic['code'], 'UNEXPECTED_ERROR')
            self.assertEqual(diagnostic['phase'], 'reconcile')
            self.assertEqual([row['type'] for row in diagnostic['exception']], ['RuntimeError', 'LookupError'])
            self.assertEqual(diagnostic['exception'][0]['frames'][-1]['function'], 'fail')
            self.assertTrue(diagnostic['exception'][0]['frames'][-1]['line'])
            self.assertEqual(diagnostic['pending_effect']['kind'], 'model')
            self.assertTrue(diagnostic['log_written'])
            for _ in range(2):
                Controller(engine.root, reasoning=peer).tick()
        self.assertEqual(len(peer.calls), 1)
        self.assertEqual(Store(engine.root).state['model_calls'], 1)
        events = recent_events(engine.root)['events']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['id'], diagnostic['id'])
        output = (engine.root / 'state.json').read_text() + (engine.root / LOG_NAME).read_text() + json.dumps(document)
        self.assertNotIn(secret, output)
        self.assertNotIn('local-variable-must-not-appear', output)
        self.assertEqual((engine.root / LOG_NAME).stat().st_mode & 0o777, 0o600)

    def test_protocol_failure_is_visible_during_bounded_repair_and_clears_after_success(self):
        self.policy['reasoning']['argv'] = [sys.executable, '-c', 'print("not-json")']
        engine = self.start()
        failed = engine.tick()
        self.assertEqual(failed['status'], 'RUNNING')
        self.assertEqual(failed['diagnostic']['code'], 'PROVIDER_PROTOCOL_ERROR')
        self.assertEqual(failed['diagnostic']['phase'], 'discovery')
        self.assertTrue(failed['diagnostic']['details']['validation'])
        engine.reasoning = InProcessProvider()
        self.assertIsNone(engine.tick()['diagnostic'])
        self.assertEqual(len(recent_events(engine.root)['events']), 1)

    def test_provider_stderr_preserves_http_details_and_redacts_resolved_credentials(self):
        secret = 'opaque-broker-value-without-a-known-prefix'
        shim = self.root / 'failing-provider.py'
        shim.write_text('import json, os, sys\n'
                       'if "--check" in sys.argv: sys.exit(0)\n'
                       'print(json.dumps({"schema":"provider-error/v1","message":"HTTP 400 invalid schema " + os.environ["COMPANY_API_KEY"],'
                       '"details":{"http_status":400,"request_id":"request-fixture"}}),file=sys.stderr)\n'
                       'sys.exit(2)\n')
        self.policy['reasoning'].update(argv=[sys.executable, str(shim)], protocol=2, model='fixture',
            credentials={'COMPANY_API_KEY': {'kind': 'env', 'name': 'CUSTOM_AUTH_SOURCE'}})
        engine = self.start()
        with patch.dict(os.environ, {'CUSTOM_AUTH_SOURCE': secret}):
            result = engine.tick()
        diagnostic = result['diagnostic']
        self.assertIn('HTTP 400 invalid schema', diagnostic['message'])
        self.assertEqual(diagnostic['details']['exit_code'], 2)
        self.assertEqual(diagnostic['details']['provider_error']['details']['http_status'], 400)
        self.assertEqual(result['model_calls'], 1)
        self.assertIsNotNone(result['pending_effect'])
        self.assertNotIn(secret, (engine.root / 'state.json').read_text() + (engine.root / LOG_NAME).read_text())
        self.assertIn('potentially charged', ' '.join(diagnostic['next_steps']))

    def test_bundled_provider_http_report_keeps_reason_and_request_id_without_headers(self):
        secret = 'provider-secret-value-12345'
        body = json.dumps({'error': {'type': 'invalid_request_error', 'message': 'Unknown model; key=' + secret}}).encode()
        exc = HTTPError('https://api.example.test/messages', 400, 'Bad Request',
                        {'request-id': 'req-fixture', 'x-secret-header': secret}, io.BytesIO(body))
        value = provider_error(exc, provider='anthropic-messages', key=secret)
        self.assertIn('Unknown model', value['message'])
        self.assertEqual(value['details']['http_status'], 400)
        self.assertEqual(value['details']['request_id'], 'req-fixture')
        self.assertNotIn(secret, json.dumps(value))
        self.assertNotIn('x-secret-header', json.dumps(value))

    def test_cli_and_ui_errors_have_specific_reason_and_shared_log_id(self):
        engine = self.start(); request, token = self.server(engine.root)
        stderr = io.StringIO()
        with patch.object(RunService, 'status', side_effect=RuntimeError('new CLI failure')), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(['status', '--state', str(engine.root)]), 2)
        cli = json.loads(stderr.getvalue())
        self.assertEqual(cli['diagnostic']['code'], 'UNEXPECTED_ERROR')
        self.assertEqual(cli['reason'], 'new CLI failure')
        with patch.object(RunService, 'decision', side_effect=RuntimeError('new UI failure ' + token)):
            status, value = request('GET', '/api/decision')
        self.assertEqual(status, 500)
        self.assertIn('new UI failure', value['reason'])
        self.assertEqual(value['diagnostic']['operation'], 'review:GET /api/decision')
        self.assertNotIn(token, json.dumps(value) + (engine.root / LOG_NAME).read_text())
        self.assertEqual(request('GET', '/api/diagnostics', authenticated=False)[0], 401)
        status, logs = request('GET', '/api/diagnostics')
        self.assertEqual(status, 200)
        self.assertEqual([event['id'] for event in logs['events']], [cli['diagnostic']['id'], value['diagnostic']['id']])

    def test_ui_can_pause_changed_runtime_using_exact_displayed_decision(self):
        engine = self.start(); request, _ = self.server(engine.root)
        with self.changed_runtime():
            status, shown = request('GET', '/api/decision')
            self.assertEqual(status, 200)
            self.assertEqual(shown['diagnostic']['code'], 'RUNTIME_CHANGED')
            body = {'action': 'pause', 'binding': None, 'decision_hash': shown['decision_hash'],
                    'reason': 'maintenance', 'accept_duplicate_cost': False}
            status, paused = request('POST', '/api/action', body)
            self.assertEqual(status, 200)
            self.assertTrue(paused['paused'])
            status, rejected = request('POST', '/api/action', body)
            self.assertEqual(status, 409)
            self.assertIn('Displayed decision changed', rejected['reason'])
            self.assertIn('diagnostic', rejected)

    def test_unreadable_state_and_logging_failure_do_not_mask_original_exception(self):
        engine = self.start()
        (engine.root / 'state.json').write_text('{"task":42,"pending":false}')
        stderr = io.StringIO()
        with patch('agent_runtime.diagnostics.os.open', side_effect=PermissionError('log read-only')), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(['status', '--state', str(engine.root)]), 2)
        result = json.loads(stderr.getvalue())
        self.assertIn('Invalid run state object', result['reason'])
        self.assertFalse(result['diagnostic']['log_written'])

    def test_rotated_log_retains_recent_events_and_does_not_follow_symlinks(self):
        from agent_runtime.diagnostics import record
        engine = self.start()
        with patch('agent_runtime.diagnostics.LOG_LIMIT', 1):
            first = record(engine.root, engine.state, exc=RuntimeError('first'))
            second = record(engine.root, engine.state, exc=RuntimeError('second'))
        self.assertEqual([v['id'] for v in recent_events(engine.root)['events']], [first['id'], second['id']])
        self.assertEqual(len(recent_events(engine.root, 1)['events']), 1)
        outside = self.root / 'outside'; outside.write_text('must stay intact')
        path = engine.root / LOG_NAME; path.unlink(); path.symlink_to(outside)
        self.assertFalse(record(engine.root, engine.state, exc=RuntimeError('third'))['log_written'])
        self.assertEqual(outside.read_text(), 'must stay intact')

    def test_doctor_reports_exact_failed_probe_without_calling_model(self):
        self.policy['reasoning']['argv'] = ['/definitely/missing/provider']
        result = diagnose(self.policy, goal())
        self.assertFalse(result['ready']); self.assertFalse(result['model_called'])
        self.assertEqual(result['reasoning']['diagnostic']['code'], 'REASONING_EXECUTABLE_UNAVAILABLE')
        self.assertEqual(result['reasoning']['diagnostic']['operation'], 'doctor:reasoning')
        self.assertEqual(result['reasoning']['diagnostic']['details']['executable'], '/definitely/missing/provider')

    def test_large_stderr_is_bounded_and_known_secret_is_redacted_before_truncation(self):
        from agent_runtime.diagnostics import safe_text
        self.assertLess(len(safe_text('a' * 2_000_000)), 2050)
        secret = 'opaque-value-' * 300
        result = safe_text('z' * 1980 + secret + ' trailing', secrets=(secret,))
        self.assertNotIn('opaque-value', result)
        self.assertIn('[redacted]', result)

    def test_environment_inference_ignores_switches_and_short_values_preserve_identifiers(self):
        from agent_runtime.diagnostics import safe_text, secret_values
        environment = {'KEYRING_ENABLED': '1', 'TOKENIZERS_PARALLELISM': 'true',
                       'MAX_TOKENS': '4000', 'CUSTOM_API_KEY': 'abc', 'GH_TOKEN': 'opaque-secret-value'}
        self.assertEqual(set(secret_values(environment)), {'abc', 'opaque-secret-value'})
        identity = '275c79ffef0e4ae393c17c1743e5e18e'
        with patch('agent_runtime.diagnostics.secret_values', return_value=['1', 'e', 'abc']):
            self.assertEqual(safe_text(identity), identity)
            self.assertEqual(safe_text('abcdef'), 'abcdef')
            self.assertEqual(safe_text('value: abc; value: 1'), 'value: [redacted]; value: [redacted]')

    def test_explicit_short_credentials_remain_masked_without_rewriting_markers(self):
        from agent_runtime.diagnostics import safe_text
        with patch('agent_runtime.diagnostics.secret_values', return_value=[]):
            self.assertEqual(safe_text('prefix1suffix', secrets=('1',)), 'prefix[redacted]suffix')
            self.assertEqual(safe_text('abc and a', secrets=('abc', 'a')), '[redacted] [redacted]nd [redacted]')
            self.assertEqual(safe_text('[redacted]', secrets=('a',)), '[redacted]')
            self.assertEqual(safe_text('[redacted]suffix', secrets=('[redacted]suffix',)), '[redacted]')
            value = safe_text('Bearer xy; password=xy; sk-longsecret123', secrets=('xy',))
            self.assertNotIn('xy', value)
            self.assertNotIn('sk-longsecret123', value)

    def test_existing_no_message_unavailable_remains_a_pre_dispatch_wait(self):
        engine = self.start()
        with patch('agent_runtime.reasoning.Reasoning.prepare', side_effect=Unavailable()):
            result = engine.tick()
        self.assertEqual(result['status'], 'WAITING_EXTERNAL')
        self.assertEqual(result['model_calls'], 0)
        self.assertIsNone(result['pending_effect'])
        self.assertEqual(result['diagnostic']['message'], 'Unavailable')


if __name__ == '__main__':
    unittest.main()
