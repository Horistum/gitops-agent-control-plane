"""Typed obligations execute in the public reference engine, not just a utility."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from reference_runtime.engine import AutonomousEngine
from reference_runtime.scenarios import build_request
from reference_runtime.contracts import validate_roadmap

ROOT = Path(__file__).resolve().parents[1]


class TypedExecutionTests(unittest.TestCase):
    def prepare(self, directory):
        root = Path(directory) / 'reference'
        for name in ('config', 'examples', 'schemas', 'reference_runtime', 'control_plane_core'):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
        product = root / 'examples/minimal-product'
        roadmap_path = product / '.agent-control/roadmap.json'
        roadmap = json.loads(roadmap_path.read_text())
        probes = json.loads((product / '.agent-control/verification-probes.json').read_text())
        compatibility = probes['baseline'][0]['id']
        roadmap['items'][0]['acceptance'] += [
            {'id': 'AC-DOC', 'text': 'Document greeting semantics', 'kind': 'documentation',
             'probe_ids': [], 'paths': ['README.md']},
            {'id': 'AC-COMPAT', 'text': 'Retain normalization behavior', 'kind': 'compatibility',
             'probe_ids': [compatibility]},
            {'id': 'AC-DELIVERY', 'text': 'Exact candidate is merged and verified', 'kind': 'delivery', 'probe_ids': []}]
        roadmap_path.write_text(json.dumps(roadmap))
        (product / 'README.md').write_text('Greeting uses normalized nonblank input.\n')
        return root, roadmap

    def test_mixed_obligations_are_deferred_before_merge_and_completed_on_exact_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.prepare(directory)
            request = build_request(root, 'autonomous-two-item', json.loads((root/'examples/goal.example.json').read_text()))
            engine = AutonomousEngine(root, request, Path(directory)/'runs')
            value = engine.run()
            self.assertEqual(value['status'], 'COMPLETED')
            events = [json.loads(line) for line in (engine.evidence/'events.jsonl').read_text().splitlines()]
            evaluations = [e['payload'] for e in events if e['type'] == 'typed-acceptance-evaluated']
            before = next(e for e in evaluations if e['stage'] == 'candidate')
            after = next(e for e in evaluations if e['stage'] == 'postmerge')
            self.assertTrue(before['passed']); self.assertFalse(before['complete'])
            self.assertEqual(next(r['status'] for r in before['rows'] if r['id'] == 'AC-DELIVERY'), 'deferred')
            self.assertTrue(after['complete'])

    def test_missing_document_is_a_real_computed_review_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.prepare(directory)
            (root/'examples/minimal-product/README.md').unlink()
            request = build_request(root, 'autonomous-two-item', json.loads((root/'examples/goal.example.json').read_text()))
            engine = AutonomousEngine(root, request, Path(directory)/'runs')
            value = engine.run()
            self.assertNotEqual(value['status'], 'COMPLETED')
            self.assertIsNone(engine.state['merge_sha'])

    def test_missing_hosted_ci_capability_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            _, roadmap = self.prepare(directory)
            roadmap['items'][0]['acceptance'].append({'id':'AC-CI', 'text':'Hosted checks', 'kind':'ci',
                'probe_ids':[], 'targets':['integration']})
            with self.assertRaisesRegex(ValueError, 'no hosted CI adapter'):
                validate_roadmap(roadmap)
