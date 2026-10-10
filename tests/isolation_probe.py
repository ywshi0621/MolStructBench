"""Actually execute filesystem/network escape probes through the production sandbox."""
import argparse
import json
import tempfile
from pathlib import Path
from runner.sandbox import inspect_workspace, execute
TASK={'id':'scibench_000001','dataset':'3d_0907','task_type':'isolation_probe','lang':'en',
      'input_representation':'text','messages':[{'role':'system','content':'Isolation test fixture.'},
      {'role':'user','content':'This is a non-scored filesystem/network isolation diagnostic.'}]}
from runner.run_agent import workspace_view

def probe(venv):
    with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
        root=Path(tmp); workspace=root/'workspace'
        for p in ('input','output','tmp'): (workspace/p).mkdir(parents=True)
        (workspace/'input/task.json').write_text(json.dumps(workspace_view(TASK)))
        (root/'private_gold_canary.txt').write_text('PRIVATE_CANARY_MUST_NOT_BE_VISIBLE')
        check=inspect_workspace(workspace)
        script='''python - <<'PY'
import os, pathlib, socket, json
from rdkit import Chem
from openbabel import openbabel
import numpy, scipy, pandas, networkx
assert networkx.__version__ == '3.4.2'
assert Chem.MolFromSmiles('CCO') is not None
assert not pathlib.Path('/mnt/c').exists()
assert not pathlib.Path('/etc/passwd').exists()
assert not pathlib.Path('/home/agent/.ssh').exists()
assert not pathlib.Path('/mnt/data').exists()
assert 'DASHSCOPE_API_KEY' not in os.environ
assert 'HARNESS_TRANSPORT_TOKEN' not in os.environ
try:
 pathlib.Path('/workspace/input/task.json').write_text('tamper')
 raise AssertionError('Input writable')
except OSError: pass
s=socket.socket(); s.settimeout(.3)
assert s.connect_ex(('1.1.1.1',443)) != 0
pathlib.Path('/workspace/output/probe.txt').write_text('ok')
print('ISOLATION_OK')
PY'''
        result=execute(workspace,venv,script)
        assert result['status']=='ok' and 'ISOLATION_OK' in result['output'], result
        escape=execute(workspace,venv,'cat '+str(root/'private_gold_canary.txt'))
        assert escape['status']=='error' and 'PRIVATE_CANARY_MUST_NOT_BE_VISIBLE' not in escape['output']
        return {'status':'passed','checks':['host-filesystem-hidden','private-canary-hidden','read-only-input',
                 'api-key-absent','transport-token-absent','network-unreachable','scientific-libraries-imported',
                 'output-writable','forbidden-filename-scan'], 'workspace':check}
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--venv',required=True); ap.add_argument('--output',required=True)
    a=ap.parse_args(); result=probe(a.venv); Path(a.output).write_text(json.dumps(result,indent=2)); print(json.dumps(result))
