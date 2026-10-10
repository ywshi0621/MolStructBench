"""Local deterministic scoring and isolated, resumable three-vote judging."""
import collections,concurrent.futures,functools,hashlib,json,os,pathlib
import yaml
from evaluator.official_scorer import aggregate,score_rows,verify_triples,expected_judge_hash
from evaluator.semantic_judge import judge_input_v1,parse_grade,OpenAICompatibleJudge
from benchmark_core.io import load_public
ROOT=pathlib.Path(__file__).resolve().parents[1]

def digest(raw):return hashlib.sha256(raw).hexdigest()
def load_jsonl(path):return [json.loads(x) for x in pathlib.Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)

def context(predictions):
    from scripts.verify_release import verify
    verify()
    public={r['id']:r for r in load_public(ROOT/'data/benchmark_288_public.jsonl')[0]}
    gold={r['id']:r for r in load_jsonl(ROOT/'data/benchmark_288_gold.jsonl')}
    ids=json.loads((ROOT/'data/selection_288.json').read_text())['selected_ids']
    records=load_jsonl(predictions)
    if len(records)!=288 or any(set(r)!={'id','prediction'} or not isinstance(r['prediction'],str) for r in records) or {r['id'] for r in records}!=set(ids):
        raise ValueError('Predictions must contain exactly 288 unique Core IDs, with id/prediction only')
    preds={r['id']:r['prediction'] for r in records}
    specs=json.loads((ROOT/'data/judge_task_specs.json').read_text())
    accepted=json.loads((ROOT/'data/accepted_variants.json').read_text())
    config=yaml.safe_load((ROOT/'configs/judge.yaml').read_text())['judge']
    prompt=(ROOT/config['prompt_template']).read_text(encoding='utf-8')
    return public,gold,ids,preds,specs,accepted,config,prompt

def cache_files(path,predictions_digest=None):
    path=pathlib.Path(path)
    if path.is_file():return [path]
    if not path.is_dir():raise ValueError('Judge cache does not exist')
    index=path/'INDEX.json'
    if index.exists():
        files=[]
        for entry in json.loads(index.read_text())['runs']:
            if predictions_digest is not None and entry['predictions_sha256']!=predictions_digest:continue
            candidate=path/entry['key']/'judge_triples.jsonl'
            if digest(candidate.read_bytes())!=entry['judge_triples_sha256']:raise ValueError('Historical Judge archive changed')
            files.append(candidate)
        return files
    if (path/'judge_triples.jsonl').exists():return [path/'judge_triples.jsonl']
    if (path/'semantic_stage/judge_triples.jsonl').exists():return [path/'semantic_stage/judge_triples.jsonl']
    checkpoints=list(path.glob('checkpoints/rep*/*.json'))
    if checkpoints:return checkpoints
    raise ValueError('Cache needs INDEX.json, judge_triples.jsonl, or checkpoints')

@functools.lru_cache(maxsize=1)
def archived_legacy_votes():
    """Old grades lack raw response text; require an exact verified archive row."""
    index=ROOT/'examples/history/INDEX.json';records=set()
    for entry in json.loads(index.read_text())['runs']:
        path=index.parent/entry['key']/'judge_triples.jsonl'
        if digest(path.read_bytes())!=entry['judge_triples_sha256']:raise ValueError('Historical Judge archive changed')
        for row in load_jsonl(path):records.add(json.dumps(row,sort_keys=True,ensure_ascii=False))
    return records

def validate_vote(row,payload,config,prompt):
    if row['id']!=payload['id'] or row['audit'].get('id')!=payload['id'] or type(row['replicate']) is not int or row['replicate'] not in (1,2,3):raise ValueError('Invalid Judge slot identity')
    parse_grade(json.dumps({k:row[k] for k in ('score','reason')}))
    verify_triples([row],expected_judge_hash(payload,config,prompt),config,digest(prompt.encode()))
    if row['audit'].get('response_text') is not None:
        text=row['audit']['response_text']
        if digest(text.encode())!=row['audit']['response_sha256'] or parse_grade(text)!={k:row[k] for k in ('score','reason')}:raise ValueError('Judge response/grade mismatch')
    elif json.dumps(row,sort_keys=True,ensure_ascii=False) not in archived_legacy_votes():
        raise ValueError('Legacy Judge grade must exactly match a verified original archive; new caches require response_text')

def write_results(output,public,gold,ids,preds,triples,accepted):
    rows=score_rows(public,gold,preds,ids,triples,accepted);result=aggregate(rows)
    result['molstructbench_score']=result['overall_score']
    result.update(publication_status='v1.0_frozen',official_v1_score=result['overall_score'],release_mode='open-gold local automatic scoring',hidden_test_set=False,human_validation_required=False)
    (output/'per_sample_scores.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    save(output/'final_results.json',result)
    return result

def score_local(predictions,output,caches=(),offline=False):
    public,gold,ids,preds,specs,accepted,config,prompt=context(predictions)
    output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=True);stage=output/'semantic_stage'
    initial=score_rows(public,gold,preds,ids,{},accepted)
    required={r['id'] for r in initial if r['score'] is None}
    payloads={sid:judge_input_v1(public[sid],gold[sid],specs,preds[sid]) for sid in required}
    identity={'normalized_predictions_sha256':digest(json.dumps(preds,sort_keys=True,ensure_ascii=False).encode()),'request_hashes':{sid:expected_judge_hash(payloads[sid],config,prompt) for sid in sorted(required)},'scoring_assets_sha256':json.loads((ROOT/'SCORER_FREEZE.json').read_text())['sha256']}
    protocol=stage/'protocol.json'
    if protocol.exists() and json.loads(protocol.read_text())!=identity:raise ValueError('Judge resume inputs/scoring assets differ; use a new output directory')
    save(protocol,identity);done={};imported=0
    def accept(row,from_cache=False):
        nonlocal imported
        sid=row['id']
        if sid not in public:raise ValueError('Unknown Judge sample ID')
        payload=payloads.get(sid) or judge_input_v1(public[sid],gold[sid],specs,preds[sid])
        validate_vote(row,payload,config,prompt)
        if sid not in required:return
        key=(sid,row['replicate'])
        if key in done and done[key]!=row:raise ValueError('Conflicting Judge records for one slot')
        if key not in done:
            done[key]=row
            if from_cache:imported+=1
    for path in sorted((stage/'checkpoints').glob('rep*/*.json')):accept(json.loads(path.read_text()))
    # A historical cache is selected by exact answer file bytes before loading.
    bundled=ROOT/'examples/history';index=json.loads((bundled/'INDEX.json').read_text()) if (bundled/'INDEX.json').exists() else {'runs':[]}
    raw_digest=digest(pathlib.Path(predictions).read_bytes())
    automatic=[bundled/entry['key'] for entry in index['runs'] if entry['predictions_sha256']==raw_digest]
    for cache in [*automatic,*caches]:
        for path in cache_files(cache,raw_digest):
            if path.is_relative_to(bundled):
                entry=next(e for e in index['runs'] if e['key']==path.parent.name)
                if digest(path.read_bytes())!=entry['judge_triples_sha256']:raise ValueError('Frozen historical votes changed')
            records=load_jsonl(path) if path.suffix=='.jsonl' else [json.loads(path.read_text())]
            for row in records:accept(row,True)
    for (sid,rep),row in done.items():save(stage/'checkpoints'/f'rep{rep}'/(sid+'.json'),row)
    def persist():
        groups=collections.defaultdict(list)
        for row in done.values():groups[row['id']].append(row)
        for sid,rows in groups.items():verify_triples(rows,identity['request_hashes'][sid],config,digest(prompt.encode()))
        (stage/'judge_triples.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for _,r in sorted(done.items())),encoding='utf-8')
        return write_results(output,public,gold,ids,preds,groups,accepted)
    result=persist();missing=[(sid,rep) for sid in ids if sid in required for rep in (1,2,3) if (sid,rep) not in done]
    errors=[];new_calls=0
    if missing and not offline and os.environ.get(config['api_key_env']):
        judge=OpenAICompatibleJudge(ROOT/'configs/judge.yaml')
        def call(slot):
            sid,rep=slot;grade,audit=judge.score(payloads[sid]);return {**grade,'replicate':rep,'audit':audit}
        with concurrent.futures.ThreadPoolExecutor(max_workers=config['concurrency']) as pool:
            futures={pool.submit(call,slot):slot for slot in missing}
            for future in concurrent.futures.as_completed(futures):
                new_calls+=1;sid,rep=futures[future]
                try:
                    row=future.result();accept(row);save(stage/'checkpoints'/f'rep{rep}'/(sid+'.json'),row)
                except Exception as exc:
                    error={'id':sid,'replicate':rep,'status':'pending','error':type(exc).__name__,'audit':getattr(exc,'audit',{})};errors.append(error);save(stage/'failed_attempts'/f'rep{rep}'/(sid+'.json'),error)
                result=persist()
                if new_calls%12==0:print(json.dumps({'judge_finished_calls':len(done),'required_calls':3*len(required),'pending_failures':len(errors)}),flush=True)
    elif missing:
        errors=[{'id':sid,'replicate':rep,'status':'pending','error':'offline_cache_missing' if offline else 'DASHSCOPE_API_KEY_missing'} for sid,rep in missing]
    attempts=[a for r in done.values() for a in r['audit'].get('attempt_log',[])];usages=[a.get('usage') or {} for a in attempts]
    usage={'completed_judge_calls':len(done),'new_judge_calls_this_invocation':new_calls,'cache_votes_imported':imported,'api_attempts':len(attempts),'api_retries':sum(max(0,len(r['audit'].get('attempt_log',[]))-1) for r in done.values()),'input_tokens':sum(u.get('prompt_tokens',0) for u in usages),'cached_input_tokens':sum((u.get('prompt_tokens_details') or {}).get('cached_tokens',0) for u in usages),'output_tokens':sum(u.get('completion_tokens',0) for u in usages),'reasoning_tokens':sum((u.get('completion_tokens_details') or {}).get('reasoning_tokens',0) for u in usages),'estimated_cost':None,'failed_call_usage_not_in_success_totals':errors}
    usage['uncached_input_tokens']=usage['input_tokens']-usage['cached_input_tokens']
    save(stage/'usage_statistics.json',usage);save(stage/'run_summary.json',{'required_calls':len(required)*3,'complete_calls':len(done),'pending':errors})
    result=persist();result['judge_statistics']={'required_calls':len(required)*3,'completed_calls':len(done),'new_calls_this_invocation':new_calls,'pending':len(errors),'usage_file':'semantic_stage/usage_statistics.json'};save(output/'final_results.json',result)
    return result
