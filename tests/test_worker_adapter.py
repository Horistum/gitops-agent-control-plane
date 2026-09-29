"""Operational adapter tests with exact Git source and a controlled app-server."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from agent_runtime.controller import Controller
from agent_runtime.io import Closed
from agent_worker import AppServerWorker
from agent_worker.capabilities import inspect_cli
from agent_worker.protocol import atomic
from runtime_support import build_product, goal, policy, InProcessProvider

class WorkerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); product=self.root/'product'; build_product(product)
        self.policy=policy(product)
        self.argv=[sys.executable,str(Path(__file__).parent/'fixtures/worker_app_server.py'),'--source-path','app.py']
        report=inspect_cli(self.argv)
        self.profile=dict(profile='codex-app-server-broker/v1',experimental=True,
            codex_version=report['codex_version'],schema_sha256=report['schema_sha256'],
            max_tool_calls=8,max_tool_bytes=100000,max_frame_bytes=100000,max_output_bytes=1000000,
            timeout_seconds=5,smoke_attestation=str(self.root/'smoke.json'))
        self.policy['reasoning'].update(kind='codex',argv=self.argv,codex_home=str(self.root/'home'),worker=self.profile)
        worker=AppServerWorker(self.profile,self.root/'home',self.root/'workers',argv=self.argv)
        atomic(Path(self.profile['smoke_attestation']),{'identity':worker.smoke_identity(),'passed':True,'model_called':True})
        engine=Controller.start(self.root/'run',self.policy,goal(),trusted_local=True)
        # Planning fixture never dispatches a model; operational policy and worker
        # stay pinned throughout. The actual production reasoning resumes below.
        engine.reasoning=InProcessProvider()
        for _ in range(20):
            if engine.task and engine.task['phase']=='developer': break
            engine.tick()
        else: self.fail(engine.summary())
        self.engine=Controller(self.root/'run')

    def test_actual_adapter_calls_broker_and_accounts_one_turn(self):
        engine=self.engine; before=engine.state['model_calls']
        result=engine.model('developer',engine.task)
        self.assertEqual(result['edits'][0]['path'],'app.py')
        self.assertEqual(result['edits'][0]['content'],'value = 3\n')
        self.assertEqual(engine.state['model_calls'],before+1)
        self.assertEqual(json.loads((self.root/'home/fixture-state.json').read_text())['turns'],1)
        from agent_runtime.usage import usage_report
        self.assertEqual(usage_report(engine.store)['reported_tokens']['input_tokens'],10)

    def test_capability_failure_before_reservation_does_not_consume_budget(self):
        engine=self.engine; before=engine.state['model_calls']
        engine.reasoning.worker.transport.argv += ['--scenario','bad-config']
        with self.assertRaises(Closed): engine.model('developer',engine.task)
        self.assertEqual(engine.state['model_calls'],before)
        self.assertFalse((self.root/'home/fixture-state.json').exists())

    def test_binding_change_rejected_without_provider_turn(self):
        engine=self.engine
        from agent_runtime.worker import binding
        from agent_runtime.contracts import ROLE_SCHEMAS
        identity=binding(engine,engine.task,'developer'); identity['head']='0'*40
        with self.assertRaises(Closed): engine.reasoning.worker.execute(
            {'phase':'developer','worker_binding':identity,'effect_id':'invalid'}, ROLE_SCHEMAS['developer'],'fixture')
        self.assertFalse((self.root/'home/fixture-state.json').exists())
