"""Test-only product and provider builders; never imported by operational code."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

TEST_RUNNER = '''import os, sys, unittest, xml.etree.ElementTree as ET
sys.path.insert(0, os.getcwd())
class Report(unittest.TestResult):
    def __init__(self):
        super().__init__(); self.xml = ET.Element('testsuite'); self.rows = {}
    def startTest(self, test):
        super().startTest(test)
        self.rows[test.id()] = ET.SubElement(self.xml, 'testcase', classname=test.__class__.__name__, name=test._testMethodName)
    def addFailure(self, test, err):
        super().addFailure(test, err); ET.SubElement(self.rows[test.id()], 'failure').text = self._exc_info_to_string(err,test)
    def addError(self, test, err):
        super().addError(test,err); ET.SubElement(self.rows[test.id()], 'error').text = self._exc_info_to_string(err,test)
    def addSkip(self, test, reason):
        super().addSkip(test,reason); ET.SubElement(self.rows[test.id()], 'skipped')
r=Report(); unittest.defaultTestLoader.discover('tests').run(r)
os.makedirs('results', exist_ok=True)
ET.ElementTree(r.xml).write('results/tests.xml')
print('tests',r.testsRun, 'failures',len(r.failures),'errors',len(r.errors))
sys.exit(0 if r.wasSuccessful() else 1)
'''


def build_product(root, *, two=False):
    root.mkdir()
    (root / 'app.py').write_text('def value():\n    return 1\n')
    if two:
        (root / 'other.py').write_text('def value():\n    return 1\n')
    (root / 'README.md').write_text('Test product. value() returns an integer.\n')
    (root / 'tests').mkdir()
    (root / 'tools').mkdir()
    (root / 'tools/test.py').write_text(TEST_RUNNER)
    (root / 'tests/test_base.py').write_text('import unittest\nfrom app import value\nclass Baseline(unittest.TestCase):\n    def test_positive(self):\n        self.assertGreater(value(), 0)\n')
    for args in [('init','-b','main'),('config','user.name','Test'),('config','user.email','test@localhost'),('add','.'),('commit','-m','Baseline')]:
        subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)


def policy(product):
    return {'schema':1,'profile':'operational-git/v1','product':str(product),'base_branch':'main',
        'allowed_paths':['*.py','README.md'],'test_paths':['tests/test_*.py'],
        'protected_paths':['tools/*'],'critical_paths':[], 'risk_ceiling':'high','auto_merge_ceiling':'low','challenge':True,
        'limits':{'model_calls':64,'repairs':3,'context_rounds':6,'context_files':24,'context_bytes':100000,'edit_bytes':100000},
        'reasoning':{'kind':'command','argv':[sys.executable,str(ROOT/'tests/runtime_fixtures/provider.py')],
                     'model':'','codex_home':'','timeout':30},
        'execution':{'kind':'trusted-local','image':'','commands':[['python3','tools/test.py']],
                     'junit':['results/*.xml'],'min_tests':1,'timeout':30,'memory_mb':512,'cpus':1,'cases':[
                         {'id':'positive','argv':['python3','-c','from app import value; print(value()>0)'],
                          'predicates':[{'id':'exit','op':'exit_code','expected':0},{'id':'positive','op':'stdout_equals','expected':'True\n'}]}]},
        'publication':{'kind':'local','repository':'','token_env':'GH_TOKEN','required_checks':[]}}


def goal(*, two=False, approval=False):
    def item(identity,path):
        return {'id':identity,'dependencies':[] if identity=='TASK-1' else ['TASK-1'], 'ready':True,'risk':'low',
                'description':'Return 2 from value()', 'context':[path],
                'acceptance':[{'id':'AC-1','text':'value returns 2','kind':'behavior','paths':[],'targets':[]}]}
    return {'schema':1,'id':'GOAL-1','objective':'Implement the approved value behavior','risk_ceiling':'high',
            'auto_merge_ceiling':'none' if approval else 'low',
            'items':[item('TASK-1','app.py')] + ([item('TASK-2','other.py')] if two else []),
            'machine_conditions':[{'id':'healthy','kind':'cli_case','case':'positive'},
                                  {'id':'behavior','kind':'criterion','item':'TASK-1','criterion':'AC-1'}]}


def proposal(payload):
    phase=payload['phase']; task=payload['task']
    result={'verdict':'ready','summary':'Evaluated actual request data','risk':'low','requested_files':[],
            'findings':[], 'acceptance_evidence':[]}
    if phase=='discovery':
        result['selected_item']=payload['eligible_items'][0]
    elif phase=='architect':
        result.update(working_set=task['context'],steps=['Implement requested behavior and verify independent tests'])
    elif phase=='test_design':
        result['scenarios']=[{'criterion_id':'AC-1','description':'Call value and require 2'}]
    elif phase=='developer':
        path=task['context'][0]
        content='def value():\n    return 2\n'
        if payload['sources'][path].get('content')==content:
            content += '# Rechecked after feedback\n'
        result['edits']=[{'path':path,'expected_sha256':payload['sources'][path]['sha256'],'delete':False,'content':content}]
    elif phase=='tester':
        module=task['context'][0].removesuffix('.py'); classname=task['id'].replace('-','')
        content=f'import unittest\nfrom {module} import value\nclass {classname}(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 2)\n'
        result['edits']=[{'path':'tests/test_'+task['id'].lower()+'.py','expected_sha256':'','delete':False,'content':content}]
        # Python unittest discovery accepts only importable names, not hyphens.
        result['edits'][0]['path']=result['edits'][0]['path'].replace('-','_')
        result['bindings']=[{'criterion_id':'AC-1','test_id':classname+':test_value','mode':'new_behavior'}]
    elif phase in {'reviewer','challenge_review','architect_accept','chief_accept'}:
        result['acceptance_evidence']=[{'criterion_id':row['id'],'status':'covered' if row['stage']=='candidate' else 'deferred',
                                       'evidence':'Controller observations in this exact request'} for row in payload['criteria']]
    return result


class InProcessProvider:
    def __init__(self, transform=None):
        self.calls=[]; self.transform=transform
    def execute(self,payload):
        self.calls.append(json.loads(json.dumps(payload)))
        result=proposal(payload)
        if self.transform:
            self.transform(payload,result,len(self.calls))
        return {'result':result,'usage':{}}
