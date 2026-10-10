"""Non-scored real tool-continuation preflight using unchanged Profile A."""
import argparse,hashlib,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scibench.cli import model_config,atomic
from scripts.verify_release import verify
from runner.run_agent import isolated_run_one
from tests.isolation_probe import probe
def verify_record(record,expected):
    successful=[]
    for tool in record.get('tool_calls',[]):
        try:result=json.loads(tool.get('output',''))
        except (ValueError,TypeError):continue
        if tool.get('tool')=='scientific_shell' and result.get('status')=='ok' and result.get('exit_code')==0 and expected in result.get('output','') and '3.4.2' in result.get('output',''):successful.append(tool)
    return record['status']=='success' and record.get('agent_model_calls',0)>=2 and bool(successful) and expected in (record.get('final_answer') or '') and '3.4.2' in (record.get('final_answer') or '') and all(r.get('original_messages_exact') for r in record['transport_checks'])
def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args();a.concurrency=1
    verify();cfg=model_config(a);key=os.environ.get(cfg['model']['api_key_env'])
    if not key:raise ValueError('Configured credential environment variable missing')
    a.profile='A';a.opencode=str(ROOT/'.runtime/bin/opencode');a.venv=str(ROOT/'.runtime/venv');a.cache=str(ROOT/'.runtime/cache')
    if subprocess.check_output([a.opencode,'--version'],text=True).strip()!='1.2.27':raise ValueError('OpenCode 1.2.27 required')
    out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True);atomic(out/'isolation_test.json',probe(a.venv))
    text='scibench-third-party-install-check';task={'id':'scibench_999999','dataset':'3d_0907','task_type':'engineering_tool_continuation_probe','lang':'en','input_representation':'text','messages':[{'role':'system','content':'Scientific tool interface acceptance test. This is not a benchmark-scored sample.'},{'role':'user','content':'Use scientific_shell to run Python, import networkx, and compute the SHA256 hex digest of the UTF-8 string '+text+'. Report the exact digest and networkx version from the tool output. You must actually use the tool.'}]}
    record=isolated_run_one(task,a,cfg,key,False);atomic(out/'trajectory.json',record)
    passed=verify_record(record,hashlib.sha256(text.encode()).hexdigest())
    atomic(out/'preflight_result.json',{'pass':passed,'non_scored':True,'native_tool_continuation':passed,'solver_model':cfg['model']['name'],'status':record['status'],'tool_calls':len(record['tool_calls']),'model_calls':record.get('agent_model_calls',0)})
    print('PASS' if passed else 'FAIL: inspect trajectory.json');sys.exit(0 if passed else 1)
if __name__=='__main__':main()
