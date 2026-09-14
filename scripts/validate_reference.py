#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, json, re, shutil, subprocess, sys, tempfile, xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; PRODUCT=ROOT/'examples'/'minimal-product'
def check(c,m):
    if not c: raise SystemExit('reference validation failed: '+m)
def run(argv,*,cwd=None):
    p=subprocess.run(argv,cwd=cwd,text=True,capture_output=True)
    if p.returncode: raise SystemExit('reference validation failed: command failed: '+' '.join(argv)+'\nSTDOUT:\n'+p.stdout[-4000:]+'\nSTDERR:\n'+p.stderr[-4000:])
    return p
def validate_publication_identity():
    for name in ('LICENSE','NOTICE','TRADEMARKS.md','CONTRIBUTING.md','SUPPORT.md','.github/SECURITY.md','docs/RELEASES.md'): check((ROOT/name).is_file(),f'publication file missing: {name}')
    check('Apache License' in (ROOT/'LICENSE').read_text(),'LICENSE is not Apache-2.0')
    notice=(ROOT/'NOTICE').read_text(); check(re.search(r'Copyright\s+\d{4}(?:-\d{4})?\s+Horistum contributors',notice) is not None,'NOTICE copyright/provenance format drift')
def validate_no_private_dependency_markers():
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(part in {'.git','.demo','__pycache__','build'} for part in path.parts) or path.suffix not in {'.md','.py','.sh','.json','.yml','.yaml'}: continue
        check('example.invalid' not in path.read_text(errors='replace'),f'placeholder public identifier remains in {path.relative_to(ROOT)}')
def validate_schemas_and_static_contracts():
    from reference_runtime.schema_validation import load_schema,validate_json_file
    for path in (ROOT/'schemas').glob('*.schema.json'): load_schema(path)
    validate_json_file(ROOT/'examples'/'goal.example.json',ROOT/'schemas'/'goal.schema.json'); validate_json_file(ROOT/'config'/'reference-policy.json',ROOT/'schemas'/'policy.schema.json')
    goal=json.loads((ROOT/'examples'/'goal.example.json').read_text()); policy=json.loads((ROOT/'config'/'reference-policy.json').read_text())
    from reference_runtime.contracts import validate_goal,validate_policy
    validate_goal(goal); validate_policy(policy); check(policy['reference_contract']=='gitops-agent-control-plane/v3','contract version drift')
    scenarios=list((ROOT/'examples'/'scenarios').glob('*.json')); check(len(scenarios)>=10,'conformance scenario coverage regressed')
    for path in scenarios:
        value=json.loads(path.read_text())
        for key in ('schema','name','expected_status','developer_fixture','tester_fixture','goal_overrides','fault_injection'): check(key in value,f'scenario fixture missing {key}: {path.name}')
        check(value['name']==path.stem,f'scenario identity drift: {path.name}')
def validate_product_baseline_without_mutation():
    before={p.relative_to(PRODUCT).as_posix():p.read_bytes() for p in PRODUCT.rglob('*') if p.is_file()}
    with tempfile.TemporaryDirectory(prefix='reference-baseline-') as d:
        copy=Path(d)/'product'; shutil.copytree(PRODUCT,copy); run([sys.executable,'-S','ci/run_tests.py'],cwd=copy); junit=copy/'build'/'test-results'/'reference'/'TEST-reference.xml'; check(junit.is_file(),'baseline JUnit missing'); tests=list(ET.parse(junit).getroot().iter('testcase')); check(len(tests)==3,f'expected 3 baseline tests, observed {len(tests)}')
    after={p.relative_to(PRODUCT).as_posix():p.read_bytes() for p in PRODUCT.rglob('*') if p.is_file()}; check(before==after,'validator mutated source example')
def validate_authority_layout():
    from reference_runtime.contracts import digest_paths,matches_any
    policy=json.loads((ROOT/'config'/'reference-policy.json').read_text()); snapshot=digest_paths(PRODUCT,policy['authority_paths']); check(bool(snapshot['files']),'authority snapshot would be empty')
    for pattern in policy['authority_paths']: check(any(matches_any(path,[pattern]) for path in snapshot['files']),f'authority pattern matched no files: {pattern}')
def validate_python_and_shell():
    for base in (ROOT/'reference_runtime',ROOT/'scripts',ROOT/'tests',PRODUCT/'src',PRODUCT/'tests',PRODUCT/'ci'):
        for path in base.rglob('*.py'): ast.parse(path.read_text(),filename=str(path))
    for path in (ROOT/'scripts').glob('*.sh'): run(['bash','-n',str(path)])
    run(['bash','-n',str(ROOT/'scripts'/'agentctl')]); run(['bash',str(ROOT/'scripts'/'bootstrap-linux.sh'),'self-test'])
def validate_docs_claims():
    readme=(ROOT/'README.md').read_text(); security=(ROOT/'docs'/'SECURITY.md').read_text(); verification=(ROOT/'docs'/'VERIFICATION.md').read_text(); check('gitops-agent-control-plane/v3' in verification,'verification docs do not name contract v3'); check('not a security sandbox' in readme.lower(),'README must disclose local executor boundary'); check('external' in security.lower() and 'anchor' in security.lower(),'SECURITY must disclose event-chain authenticity boundary')
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--fast',action='store_true'); a=p.parse_args(argv); validate_publication_identity(); validate_no_private_dependency_markers(); validate_schemas_and_static_contracts(); validate_authority_layout(); validate_python_and_shell(); validate_docs_claims();
    if not a.fast: validate_product_baseline_without_mutation()
    print(json.dumps({'passed':True,'reference_contract':'gitops-agent-control-plane/v3','licensed':'Apache-2.0','provenance':'Horistum','baseline_tests':0 if a.fast else 3,'source_tree_mutated':False},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
