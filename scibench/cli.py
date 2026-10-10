"""OpenCode agent entry point and local automatic scoring."""
import argparse,hashlib,importlib.metadata,json,os,pathlib,shutil,subprocess,sys,time,urllib.request
import yaml
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def atomic(p,obj):
    p=pathlib.Path(p);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(p)
def model_config(a):
    path=pathlib.Path(a.config) if a.config else ROOT/'configs/chat.json'
    cfg=yaml.safe_load(path.read_text())
    cfg['model']['name']=a.model
    if not cfg['model'].get('tool_call'):raise ValueError('UNSUPPORTED: Profile A requires native function tool calling; no simulated text-tool fallback.')
    from runner.provider_adapters import ProviderAdapter
    ProviderAdapter(cfg['model'])
    policy=json.loads((ROOT/'configs/runtime_policy.json').read_text())
    for field,value in policy.items():
        if cfg['runtime'].get(field)!=value:raise ValueError('Uniform Profile A runtime mismatch: '+field)
    if cfg['model']['max_tokens']!=32768:raise ValueError('Uniform output-token cap must be 32768')
    if not 1<=a.concurrency<=3:raise ValueError('Sample concurrency must be 1..3')
    cfg['runtime']['concurrency']=a.concurrency
    return cfg
def evaluate(a):
    from scripts.verify_release import verify
    verify()
    from runner.adapter import load_public,prompt_hash
    from runner.queue import run_queue,remaining
    from runner.usage import summarize
    from tests.isolation_probe import probe
    cfg=model_config(a);rows,info=load_public(a.public_data or ROOT/'data/benchmark_288_public.jsonl')
    version=json.loads((ROOT/'VERSION.json').read_text())
    if info['public_jsonl_sha256']!=version['public_data_sha256']:raise ValueError('Public input differs from Core-288 release')
    selected=rows
    if a.ids:
        ids=pathlib.Path(a.ids).read_text().splitlines()
        if not a.smoke:raise ValueError('Subset inference requires --smoke and is ineligible for full Core-288 headline')
        if len(ids)!=len(set(ids)) or not set(ids)<={r['id'] for r in rows}:raise ValueError('Invalid smoke IDs')
        byid={r['id']:r for r in rows};selected=[byid[sid] for sid in ids]
    if a.limit:
        if not a.smoke:raise ValueError('--limit requires --smoke')
        selected=selected[:a.limit]
    if a.smoke and not (a.limit or a.ids):raise ValueError('Smoke requires --limit or --ids')
    key=os.environ.get(cfg['model']['api_key_env'])
    if not key:raise ValueError('Credential env missing: '+cfg['model']['api_key_env'])
    a.profile='A';a.opencode=str(pathlib.Path(a.opencode or ROOT/'.runtime/bin/opencode').resolve())
    a.venv=str(pathlib.Path(a.scientific_venv or ROOT/'.runtime/venv').resolve());a.cache=str(pathlib.Path(a.cache or ROOT/'.runtime/cache').resolve())
    if subprocess.check_output([a.opencode,'--version'],text=True).strip()!='1.2.27':raise ValueError('OpenCode 1.2.27 required')
    out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True);(out/'logs').mkdir(exist_ok=True)
    identity={'benchmark_version':version['version'],'public_data_sha256':info['public_jsonl_sha256'],
              'selection_sha256':version['selection_sha256'],'config':cfg,'profile':'A','smoke':a.smoke,
              'ids':[r['id'] for r in selected],'prompt_hashes':{r['id']:prompt_hash(r['messages']) for r in selected},
              'source_sha256':{str(p.relative_to(ROOT)):sha(p) for folder in ('scibench','runner') for p in (ROOT/folder).rglob('*.py')},
              'sandbox_scope':'scientific_shell bubblewrap; OpenCode process is host-side under a restricted environment, not an OS security boundary'}
    manifest=out/'submission_manifest.json'
    if manifest.exists():
        if not a.resume or json.loads(manifest.read_text())!=identity:raise ValueError('Use --resume with identical config/input/source')
    elif a.resume:raise ValueError('No checkpoint to resume')
    atomic(manifest,identity);atomic(out/'isolation_test.json',probe(a.venv))
    logs=[json.loads(p.read_text()) for p in (out/'logs').glob('*/trajectory.json')];remaining(selected,logs)
    def checkpoint():
        byid={r['id']:r for r in logs};tmp=out/'predictions.jsonl.tmp'
        tmp.write_text(''.join(json.dumps({'id':r['id'],'prediction':byid[r['id']].get('final_answer') or ''},ensure_ascii=False)+'\n' for r in selected if r['id'] in byid),encoding='utf-8');tmp.replace(out/'predictions.jsonl')
        usage=summarize(logs,cfg.get('pricing'));atomic(out/'usage_statistics.json',usage)
        atomic(out/'submission_receipt.json',{'predictions_sha256':sha(out/'predictions.jsonl'),'completed':len(logs),'expected':len(selected),'smoke':a.smoke})
        print(json.dumps({'completed':len(logs),'expected':len(selected),'usage':usage['totals']}),flush=True)
    run_queue(selected,logs,out,a,cfg,key,checkpoint);checkpoint()
def score(a):
    from scibench.local_score import score_local
    result=score_local(a.predictions,a.output,a.judge_cache,a.offline)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    return 3 if result['pending_count'] else 0

def main(argv=None):
    parser=argparse.ArgumentParser(prog='molstructbench');sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('eval');p.add_argument('--model',required=True);p.add_argument('--config');p.add_argument('--output',required=True)
    for field in ('public-data','opencode','scientific-venv','cache','ids'):p.add_argument('--'+field)
    p.add_argument('--limit',type=int);p.add_argument('--smoke',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--concurrency',type=int,default=3)
    p=sub.add_parser('score');p.add_argument('--predictions',required=True);p.add_argument('--output',required=True);p.add_argument('--judge-cache',action='append',default=[]);p.add_argument('--offline',action='store_true');p.add_argument('--resume',action='store_true',help='Reuse validated checkpoints; also automatic for the same inputs')
    a=parser.parse_args(argv)
    try:return evaluate(a) if a.command=='eval' else score(a)
    except Exception as exc:parser.exit(2,type(exc).__name__+': '+str(exc)+'\n')
if __name__=='__main__':raise SystemExit(main())
