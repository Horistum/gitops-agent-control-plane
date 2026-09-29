import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_runtime.controller import Controller
from agent_runtime.actions import action
from agent_runtime.git import GitRepository
from agent_runtime.github import GitHub, NoRedirect
from agent_runtime.io import Closed, Unavailable, canonical, run
from agent_runtime.reasoning import Reasoning
from agent_runtime.verification import Verification, junit
from runtime_support import build_product, goal, policy, InProcessProvider


class FakeGitHubService:
    """In-memory HTTP contract peer; Git effects use a real bare remote."""
    def __init__(self,remote):
        self.remote=remote; self.pr=None; self.posts=0; self.merges=0
        self.after_publish_failure=False; self.after_merge_failure=False
        self.after_close_failure=False; self.closes=0; self.merge_on_close=False
    def __call__(self,path,method,body):
        if self.pr and self.pr['state'] == 'open':
            self.pr['head']['sha'] = self.remote.resolve(self.branch)
            self.pr['base']['sha'] = self.remote.resolve('main')
        if path.endswith('/protection'):
            return {'required_status_checks':{'strict':True,'checks':[{'context':'tests','app_id':15368}]},
                    'required_pull_request_reviews':{'required_approving_review_count':0},
                    'required_conversation_resolution':{'enabled':True},'allow_force_pushes':{'enabled':False},
                    'allow_deletions':{'enabled':False},'enforce_admins':{'enabled':True}}
        if '/check-runs?' in path:
            head=path.split('/commits/')[1].split('/')[0]
            return {'check_runs':[{'id':1,'name':'tests','head_sha':head,'app':{'id':15368},'status':'completed','conclusion':'success'}]}
        if '/pulls?' in path: return [self.pr] if self.pr else []
        if path.endswith('/pulls') and method=='POST':
            self.posts+=1
            self.branch=body['head']
            self.pr={'number':1,'html_url':'https://github.com/owner/product/pull/1','state':'open','draft':False,
                     'head':{'sha':self.remote.resolve(body['head']),'repo':{'full_name':'owner/product'}},
                     'base':{'sha':self.remote.resolve('main'),'ref':'main','repo':{'full_name':'owner/product'}},
                     'merged_at':None,'mergeable':True,'mergeable_state':'clean'}
            if self.after_publish_failure:
                self.after_publish_failure=False; raise Unavailable('response lost after create')
            return self.pr
        if path.endswith('/pulls/1'):
            if method=='PATCH':
                self.closes+=1
                if self.merge_on_close:
                    self('/repos/owner/product/pulls/1/merge','PUT',{'sha':self.pr['head']['sha'],'merge_method':'merge'})
                else:
                    self.pr['state']='closed'
                if self.after_close_failure:
                    self.after_close_failure=False; raise Unavailable('response lost after close')
            return copy.deepcopy(self.pr)
        if path.endswith('/pulls/1/merge'):
            assert method=='PUT' and body=={'sha':self.pr['head']['sha'],'merge_method':'merge'}
            self.merges+=1
            revision=self.remote.merge_local(self.pr['base']['sha'],self.pr['head']['sha'],'service-merge')
            self.pr.update(merged_at='2026-01-01T00:00:00Z',merge_commit_sha=revision,state='closed')
            if self.after_merge_failure:
                self.after_merge_failure=False; raise Unavailable('response lost after merge')
            return {'merged':True,'sha':revision}
        raise AssertionError((path,method,body))


class OperationalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.product=self.root/'product';build_product(self.product)
        self.policy=policy(self.product)

    def test_failed_candidate_ci_repairs_and_extends_same_pr_without_replacing_frozen_tests(self):
        remote=self.root/'repair-remote.git'
        run(['git','clone','--bare',str(self.product),str(remote)])
        engine=Controller.start(self.root/'repair-run',self.policy,goal(),trusted_local=True)
        engine.repo.text('remote','set-url','origin',str(remote))
        service=FakeGitHubService(GitRepository(remote,'main'))
        failed=[]
        def transport(path,method,body):
            result=service(path,method,body)
            if '/check-runs?' in path:
                head=path.split('/commits/')[1].split('/')[0]
                if not failed: failed.append(head)
                if head == failed[0]: result['check_runs'][0]['conclusion']='failure'
            return result
        publication={'repository':'owner/product','token_env':'GH_TOKEN','required_checks':[{'name':'tests','app_id':15368}]}
        provider=InProcessProvider()
        for _ in range(100):
            engine=Controller(engine.root,reasoning=provider,github=GitHub(publication,'main',transport=transport))
            result=engine.tick()
            if result['status']!='RUNNING': break
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(service.posts,1); self.assertEqual(service.merges,1)
        self.assertEqual(len([p for p in provider.calls if p['phase']=='tester']),1)
        self.assertEqual(len([p for p in provider.calls if p['phase']=='developer']),2)
        task=engine.state['archive'][0]
        engine.repo.text('merge-base','--is-ancestor',failed[0],task['head'])
        self.assertEqual(task['repairs'],1)

    def test_retirement_recovers_lost_close_and_reconciles_concurrent_merge(self):
        for merge_on_close in (False, True):
            with self.subTest(merge_on_close=merge_on_close):
                remote=self.root/('remote-'+str(merge_on_close)+'.git')
                run(['git','clone','--bare',str(self.product),str(remote)])
                engine=Controller.start(self.root/('run-'+str(merge_on_close)),self.policy,goal(),trusted_local=True)
                engine.repo.text('remote','set-url','origin',str(remote))
                service=FakeGitHubService(GitRepository(remote,'main'))
                publication={'repository':'owner/product','token_env':'GH_TOKEN','required_checks':[{'name':'tests','app_id':15368}]}
                def restore(root):
                    return Controller(root,reasoning=InProcessProvider(),github=GitHub(publication,'main',transport=service))
                for _ in range(60):
                    engine=restore(engine.root); result=engine.tick()
                    self.assertEqual(result['status'],'RUNNING',result)
                    if result['phase']=='merge': break
                self.assertEqual(result['phase'],'merge')
                service.after_close_failure=True; service.merge_on_close=merge_on_close
                with patch('agent_runtime.actions.Controller',side_effect=restore), self.assertRaises(Unavailable):
                    action(engine.root,'cancel')
                for _ in range(10):
                    engine=restore(engine.root);result=engine.tick()
                    if result['status']!='RUNNING': break
                self.assertEqual(result['status'],'CANCELLED',result)
                self.assertEqual(service.closes,1)
                self.assertFalse(engine.state.get('pending'))
                self.assertFalse(engine.state.get('owner_intent'))
                self.assertEqual(bool(engine.state['completed']),merge_on_close)
                if merge_on_close:
                    self.assertTrue(engine.state['archive'][0]['postmerge_evidence']['passed'])

    def test_real_git_remote_and_github_contract_reconcile_lost_publish_and_merge_responses(self):
        remote=self.root/'remote.git'
        run(['git','clone','--bare',str(self.product),str(remote)])
        engine=Controller.start(self.root/'run',self.policy,goal(),trusted_local=True)
        engine.repo.text('remote','set-url','origin',str(remote))
        service=FakeGitHubService(GitRepository(remote,'main'))
        service.after_publish_failure=service.after_merge_failure=True
        publication={'repository':'owner/product','token_env':'GH_TOKEN','required_checks':[{'name':'tests','app_id':15368}]}
        provider=InProcessProvider()
        waiting=0; clock=1000
        for _ in range(100):
            engine=Controller(engine.root,reasoning=provider,github=GitHub(publication,'main',transport=service),
                              clock=lambda: clock)
            result=engine.tick()
            if result['status']=='WAITING_EXTERNAL':
                waiting+=1
                clock=engine.state.get('technical_recovery', {}).get('next_attempt', clock + 1)
                continue
            if result['status']!='RUNNING':break
        self.assertEqual(result['status'],'COMPLETED',result)
        self.assertEqual(service.posts,1)
        self.assertEqual(service.merges,1)
        self.assertEqual(waiting,2)
        task=engine.state['archive'][0]
        self.assertEqual(task['postmerge_checks']['sha'],task['merge_sha'])
        self.assertEqual(task['postmerge_evidence']['head'],task['merge_sha'])

    def test_wrong_app_stale_head_and_latest_failed_check_cannot_pass(self):
        config={'repository':'owner/product','token_env':'GH_TOKEN','required_checks':[{'name':'tests','app_id':15368}]}
        head='a'*40
        row={'id':1,'name':'tests','head_sha':head,'app':{'id':999},'status':'completed','conclusion':'success'}
        service=lambda *args:{'check_runs':[row]}
        github=GitHub(config,'main',transport=service)
        self.assertFalse(github.checks(head)['passed'])
        row['app']['id']=15368;row['head_sha']='b'*40
        with self.assertRaises(Closed):github.checks(head)
        row['head_sha']=head
        newer={**row,'id':2,'conclusion':'failure'}
        github.transport=lambda *args:{'check_runs':[row,newer]}
        self.assertFalse(github.checks(head)['passed'])

    def test_github_redirect_never_forwards_credential(self):
        with self.assertRaises(Closed):NoRedirect().redirect_request(None,None,302,'found',{},'https://untrusted.example')

    def test_podman_worker_uses_isolation_and_cleanup(self):
        config=copy.deepcopy(self.policy['execution']);config.update(kind='podman',image='test@sha256:'+'a'*64)
        calls=[]
        def process(argv,**kwargs):
            calls.append((argv,kwargs));return subprocess.CompletedProcess(argv,0,b'',b'')
        with patch('agent_runtime.verification.run',side_effect=process):
            Verification(config).command(['python3','tools/test.py'],self.product)
        argv=calls[0][0]
        for flag in ('--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--userns=keep-id','--pull=never'):
            self.assertIn(flag,argv)
        self.assertNotIn('GH_TOKEN',' '.join(argv))
        self.assertEqual(calls[-1][0][:4],['podman','rm','--force','--ignore'])

    def test_podman_missing_resource_delegation_fails_before_model_or_product_execution(self):
        config=copy.deepcopy(self.policy['execution']);config.update(kind='podman',image='test@sha256:'+'a'*64)
        host={'security':{'rootless':True},'cgroupVersion':'v2','cgroupManager':'systemd',
              'cgroupControllers':['memory','pids']}
        def response(argv,**kwargs):
            return subprocess.CompletedProcess(argv,0,canonical({'host':host}),b'')
        with patch('agent_runtime.verification.run',side_effect=response) as process:
            with self.assertRaisesRegex(Closed,'delegated cpu'):
                Verification(config).preflight()
            self.assertEqual(process.call_count,1)
            host['cgroupControllers'].append('cpu')
            self.assertEqual(Verification(config).preflight()['resource_limits'],'delegated')

    def test_no_git_credentials_or_api_keys_reach_real_command_provider(self):
        script=self.root/'provider.py'
        script.write_text('import json,os,sys\nr=json.load(sys.stdin)\nassert not any(x in os.environ for x in ["GH_TOKEN","GITHUB_TOKEN","OPENAI_API_KEY","CODEX_API_KEY","SSH_AUTH_SOCK"])\nassert not os.path.exists(".git")\nprint(json.dumps({"verdict":"ready","summary":"isolated","risk":"low","requested_files":[],"findings":[],"acceptance_evidence":[],"selected_item":"TASK-1"}))\n')
        config=self.policy['reasoning'];config['argv']=[sys.executable,str(script)]
        with patch.dict(os.environ,{'GH_TOKEN':'test-token','OPENAI_API_KEY':'test-key','SSH_AUTH_SOCK':'test-socket'}):
            self.assertEqual(Reasoning(config).execute({'phase':'discovery'})['result']['verdict'],'ready')

    def test_codex_uses_official_data_only_flags_and_rejects_tool_events(self):
        script=self.root/'codex.py'
        script.write_text('''import json,sys,os
args=sys.argv[1:]
assert '--ignore-user-config' in args and '--ignore-rules' in args and '--ephemeral' in args
assert args[args.index('--sandbox')+1]=='read-only'
assert 'features.shell_tool=false' in args and 'features.unified_exec=false' in args
assert 'forced_login_method="chatgpt"' in args
assert 'GH_TOKEN' not in os.environ and 'OPENAI_API_KEY' not in os.environ
request=json.load(sys.stdin)
with open(args[args.index('--output-last-message')+1],'w') as f:
 json.dump({'verdict':'ready','summary':'protocol smoke','risk':'low','requested_files':[],'findings':[],'acceptance_evidence':[],'selected_item':'TASK-1'},f)
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1}}))
''')
        config={**self.policy['reasoning'],'kind':'codex','argv':[sys.executable,str(script)],'codex_home':str(self.root/'codex-home')}
        self.assertEqual(Reasoning(config).execute({'phase':'discovery'})['result']['verdict'],'ready')
        script.write_text(script.read_text()+"print(json.dumps({'type':'item.completed','item':{'type':'command_execution'}}))\n")
        with self.assertRaises(Closed):Reasoning(config).execute({'phase':'discovery'})

    def test_process_deadline_output_limit_and_bidirectional_io(self):
        with self.assertRaises(Unavailable):run([sys.executable,'-c','import time;time.sleep(10)'],timeout=.05)
        with self.assertRaises(Closed):run([sys.executable,'-c','print("x"*100000)'],limit=1000)
        data=b'x'*100000
        result=run([sys.executable,'-c','import sys;sys.stdout.write("y"*100000);sys.stdout.flush();print(len(sys.stdin.read()))'],data=data)
        self.assertTrue(result.stdout.endswith(b'100000\n'))

    def test_junit_duplicate_and_symlink_reports_rejected(self):
        reports=self.product/'results';reports.mkdir()
        (reports/'tests.xml').write_text('<testsuite><testcase classname="A" name="b"/><testcase classname="A" name="b"/></testsuite>')
        with self.assertRaises(Closed):junit(self.product,['results/*.xml'])
        (reports/'tests.xml').unlink();(reports/'tests.xml').symlink_to(self.product/'README.md')
        with self.assertRaises(Closed):junit(self.product,['results/*.xml'])


if __name__=='__main__':unittest.main()
