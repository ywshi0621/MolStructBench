import copy
import argparse
import importlib.metadata
import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import yaml
from runner.adapter import prompt_hash, digest
from runner.collector import Collector
from runner.gateway import Gateway
from runner.sandbox import inspect_workspace, execute

ROOT = Path(__file__).resolve().parents[1]

def source_hashes():
    paths=[ROOT/'benchmark_adapter.py']
    for name in ('runner','opencode','evaluator','tests','scripts','tools'):
        paths.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and p.suffix in ('.py','.ts'))
    return {str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in sorted(paths)}

def write_json(path, obj):
    path=Path(path)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)

def workspace_view(task):
    # The scientific tool gets only the same semantic prompt seen by the model.
    # Dataset/task/subtask metadata stay runner-side so tools cannot exploit extra labels.
    return {'id': task['id'], 'messages': task['messages']}

def make_config(gateway, profile, model, settings):
    allow = {'*':'deny'}
    if profile != 'none': allow['scientific_shell']='allow'
    if profile == 'B': allow['websearch']='allow'
    config = {'$schema':'https://opencode.ai/config.json','model':'benchmark/'+model['name'],
      'small_model':'benchmark/'+model['name'], 'enabled_providers':['benchmark'],
      'share':'disabled','snapshot':False,'autoupdate':False,
      'compaction':{'auto':False,'prune':False}, 'permission':allow,
      'plugin':[],
      'provider':{'benchmark':{'npm':'@ai-sdk/openai-compatible','name':'Benchmark transport',
        'options':{'baseURL':gateway.url,'apiKey':'{env:HARNESS_TRANSPORT_TOKEN}'},
        'models':{model['name']:{'name':model['name'],
             'tool_call':model.get('tool_call', True),
             'reasoning':model.get('reasoning', bool(model.get('reasoning_effort') or model.get('enable_thinking'))),
             'temperature':model.get('temperature') is not None,
             'limit':{'context':model.get('context_window',1000000),'output':model['max_tokens']}}}}},
      'agent':{'benchmark':{'mode':'primary','prompt':model.get('runtime_instruction',''),
                  'permission':allow}, 'title':{'disable':True},'summary':{'disable':True}},
      'default_agent':'benchmark','lsp':False,'formatter':False}
    if model.get('temperature') is not None:
        config['agent']['benchmark']['temperature']=model['temperature']
    if profile != 'none':
        config['mcp'] = {'scientific': {'type':'local',
          'command':[settings['python'],'-m','runner.mcp_scientific'],
          'environment':{'PYTHONPATH':settings['harness'],
             'SCIBENCH_WORKSPACE':settings['workspace'],
             'SCIBENCH_VENV':settings['venv'],
             'SCIBENCH_TOOL_TIMEOUT':str(settings['tool_timeout_seconds']),
             'SCIBENCH_MAX_TOOL_CALLS':str(settings['max_tool_calls'])},
          'enabled':True,'timeout':(settings['tool_timeout_seconds']+10)*1000}}
    return config

def run_one(task, args, cfg, key, mock=False):
    runtime, model = cfg['runtime'], cfg['model']
    collector = Collector()
    started = time.monotonic()
    failure = None
    # OpenCode's SQLite sessions and logs are confined to tmpfs and then destroyed.
    with tempfile.TemporaryDirectory(prefix='scibench-', dir='/dev/shm') as temp:
        base = Path(temp)
        workspace = base/'workspace'
        for name in ('input','output','tmp'): (workspace/name).mkdir(parents=True)
        write_json(workspace/'input/task.json', workspace_view(task))
        isolation = inspect_workspace(workspace)
        control = base/'control'; control.mkdir()
        settings = {'profile':args.profile,'workspace':str(workspace),'venv':str(Path(args.venv).resolve()),
                    'python':sys.executable,'harness':str(ROOT),
                    'max_tool_calls':runtime['max_tool_calls'],'tool_timeout_seconds':runtime['tool_timeout_seconds']}
        write_json(control/'settings.json', settings)
        with Gateway(model, runtime, task, args.profile, key, mock) as gateway:
            write_json(control/'opencode.json', make_config(gateway, args.profile, model, settings))
            env = {'PATH':str(Path(args.opencode).resolve().parent)+':/usr/bin:/bin',
              'HOME':str(base/'home'),'XDG_DATA_HOME':str(base/'data'),
              'XDG_CONFIG_HOME':str(base/'config'),'XDG_STATE_HOME':str(base/'state'),
              'XDG_CACHE_HOME':str(Path(args.cache).resolve()),'TMPDIR':str(base/'tmp'),
              'LANG':'C.UTF-8','LC_ALL':'C.UTF-8',
              'OPENCODE_CONFIG':str(control/'opencode.json'),
              'OPENCODE_DISABLE_PROJECT_CONFIG':'true','OPENCODE_DISABLE_CLAUDE_CODE':'true',
              'OPENCODE_DISABLE_DEFAULT_PLUGINS':'true','OPENCODE_DISABLE_AUTOUPDATE':'true',
              'OPENCODE_DISABLE_SHARE':'true','OPENCODE_ENABLE_EXA':'true' if args.profile=='B' else 'false',
              'HARNESS_TASK':str(workspace/'input/task.json'),'HARNESS_SETTINGS':str(control/'settings.json'),
              'HARNESS_TRANSPORT_TOKEN':gateway.token}
            for name in ('home','data','config','state','tmp'): (base/name).mkdir()
            p = subprocess.Popen([args.opencode,'run','--format','json','--agent','benchmark',
                  '--title',task['id'],'--model','benchmark/'+model['name']],
                  cwd=control, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                  stderr=subprocess.DEVNULL, start_new_session=True)
            # The gateway rewrites OpenCode's provider-facing initial messages to the frozen benchmark pair.
            p.stdin.write(task['messages'][1]['content'].encode()); p.stdin.close()
            selector = selectors.DefaultSelector(); selector.register(p.stdout, selectors.EVENT_READ)
            buffer = b''
            try:
                while selector.get_map():
                    if gateway.completed_finalization.is_set():break
                    if gateway.status:break
                    if time.monotonic()-started > runtime['sample_timeout_seconds']:
                        failure='sample_timeout'; break
                    for event, _ in selector.select(.2):
                        chunk=os.read(event.fileobj.fileno(),65536)
                        if not chunk: selector.unregister(event.fileobj); continue
                        buffer += chunk
                        while b'\n' in buffer:
                            line, buffer=buffer.split(b'\n',1)
                            try: collector.accept(json.loads(line))
                            except (ValueError, TypeError): pass
                        if len(buffer)>2*1024**2: failure='event_size_limit'; break
                    if failure: break
            finally:
                gateway.cancelled.set()
                if p.poll() is None:
                    try: p.wait(timeout=3)
                    except subprocess.TimeoutExpired: os.killpg(p.pid, signal.SIGKILL); p.wait()
                selector.close()
            records = copy.deepcopy(gateway.records)
            budget = gateway.budget.summary()
            finalization_answer = gateway.finalization_answer
            failure = failure or gateway.status or ('opencode_exit_error' if p.returncode and not finalization_answer else None)
    final = (finalization_answer or collector.final()) if not failure else None
    if not final and not failure: failure='missing_terminal_final'
    return {'id':task['id'],'dataset':task['dataset'],'task_type':task['task_type'],
            'prompt_hash':prompt_hash(task['messages']),'profile':args.profile,
            'status':terminal_status(final,failure,budget),'failure':failure,
            **budget,
            'final_answer':final,'model_response':final,'tool_calls':list(collector.tools.values()),
            'token_usage':collector.tokens,'latency_seconds':round(time.monotonic()-started,3),
            'transport_checks':records,'isolation':isolation,'mock':mock}

TERMINAL_STATUSES={'success','forced_finalization','model_failure','timeout','infra_failure'}

def terminal_status(final,failure,budget):
    if final:return 'forced_finalization' if budget.get('forced_finalization_triggered') else 'success'
    if failure=='sample_timeout':return 'timeout'
    if failure in ('budget_failure','budget_exhausted','missing_terminal_final','opencode_exit_error'):return 'model_failure'
    return 'infra_failure'

def isolated_run_one(task,args,cfg,key,mock=False):
    try:return run_one(task,args,cfg,key,mock)
    except Exception as exc:
        # Only exception class is logged: an SDK exception can include credentials.
        return {'id':task['id'],'dataset':task['dataset'],'task_type':task['task_type'],
            'prompt_hash':prompt_hash(task['messages']),'profile':args.profile,
            'status':'infra_failure','failure':'unhandled_'+type(exc).__name__,
            'final_answer':None,'model_response':None,'tool_calls':[],
            'token_usage':{'input':0,'output':0,'reasoning':0,'cache_read':0,'cache_write':0},
            'latency_seconds':0,'transport_checks':[],'isolation':{'status':'unknown'},'mock':mock,
            'usage_incomplete':True,'soft_budget_triggered':False,'forced_finalization_triggered':False,
            'agent_model_calls':0,'forced_finalization_calls':0,'finalization_status':'not_reached'}

if __name__ == '__main__':
    raise SystemExit('Use scibench eval; legacy 940 CLI removed from this release.')
