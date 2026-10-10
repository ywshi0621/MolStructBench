"""SciBench Core-288 official aggregation and offline scoring interface.

No model-specific adjustments or human override scores are accepted.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import statistics
from evaluator.deterministic_r2 import deterministic_score

DATASETS = ('3d_0907','3d_to_2d_v7_5_final','pure2d_full_rdkit2024035_sft_v4_pairwisefix_groundingaligned_v12_20260824')

def median_three(records):
    if len(records)!=3 or {r['replicate'] for r in records}!={1,2,3}:raise ValueError('Exactly three independent replicates required')
    if any(type(r.get('score')) is not int or r['score'] not in (0,1,2) for r in records):raise ValueError('Invalid judge score')
    return statistics.median(r['score'] for r in records)/2

def expected_judge_hash(payload,config,prompt):
    from evaluator.judge_wire import request_bytes
    return hashlib.sha256(request_bytes(payload,config,prompt)).hexdigest()


def verify_triples(records,request_hash,config,prompt_hash):
    for row in records:
        audit=row['audit']
        if row['judge_model']!=config['model'] or audit['request_sha256']!=request_hash or audit['prompt_template_sha256']!=prompt_hash:
            raise ValueError('Judge identity, prompt or anonymous input mismatch')
        for field in ('temperature','reasoning_effort','enable_thinking'):
            if audit.get(field)!=config.get(field):raise ValueError('Judge parameter mismatch')
    if len({row['timestamp'] for row in records})!=len(records):raise ValueError('Replicates must be independent calls')

def aggregate(rows):
    units=collections.defaultdict(list)
    for row in rows:units[(row['dataset'],row['task_type'])].append(row)
    if len(rows)!=288 or len({r['id'] for r in rows})!=288 or len(units)!=48 or any(len(v)!=6 for v in units.values()):
        raise ValueError('Expected fixed 288 IDs / 48 units / 6 samples per unit')
    datasets=collections.defaultdict(list);tasks={}
    for (dataset,task),group in sorted(units.items()):
        score=None if any(r['score'] is None for r in group) else statistics.mean(r['score'] for r in group)
        tasks[dataset+'::'+task]={'score':score,'sample_count':6,'pending':sum(r['score'] is None for r in group)}
        datasets[dataset].append(score)
    if set(datasets)!=set(DATASETS):raise ValueError('Dataset identities differ from official Core-288')
    ds={d:None if any(s is None for s in scores) else statistics.mean(scores) for d,scores in datasets.items()}
    complete=all(score is not None for score in ds.values())
    def secondary(metric):
        group=[r for r in rows if r['metric_type']==metric] if metric=='semantic_judge' else [r for r in rows if r['metric_type']!='semantic_judge']
        return None if not group or any(r['score'] is None for r in group) else statistics.mean(r['score'] for r in group)
    return {'scibench_score':statistics.mean(ds.values()) if complete else None,
            'overall_score':statistics.mean(ds.values()) if complete else None,
            'aggregation':'task-unit mean -> dataset mean -> equal mean of three datasets',
            'dataset_breakdown':ds,'task_breakdown':tasks,
            'deterministic_score':secondary('deterministic'),'semantic_score':secondary('semantic_judge'),
            'micro_score':statistics.mean(r['score'] for r in rows) if complete else None,
            'tool_statistics':{'available':False},
            'pending_count':sum(r['score'] is None for r in rows),'evaluation_status':'complete' if complete else 'pending'}

def score_rows(public,gold,predictions,ids,triples,accepted):
    if set(predictions)!=set(ids):raise ValueError('Predictions must contain exactly the fixed selection')
    rows=[]
    for sid in ids:
        g=gold[sid];pred=predictions[sid];diagnostics={};stage='deterministic'
        variants=accepted.get(sid,{}).get('accepted_variants') or [g]
        grades=[deterministic_score(pred,v) for v in variants]
        score=max((s for s,_ in grades if s is not None),default=None)
        if score is not None:diagnostics=next(d for s,d in grades if s==score)
        if score is None:
            stage='semantic' if g['metric_type']=='semantic_judge' else 'name_identity_fallback'
            records=triples.get(sid,[])
            score=median_three(records) if len(records)==3 else None
            diagnostics={'judge_replicates':len(records),'judge_scores':[r['score'] for r in records]}
        rows.append({'id':sid,'dataset':public[sid]['dataset'],'task_type':public[sid]['task_type'],
                     'metric_type':g['metric_type'],'score':score,'stage':stage,'diagnostics':diagnostics,
                     'prediction_sha256':hashlib.sha256(pred.encode()).hexdigest()})
    return rows

def read_jsonl(path):
    return [json.loads(line) for line in pathlib.Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]

def mapping(rows,key,value=None):
    if len({r[key] for r in rows})!=len(rows):raise ValueError('Duplicate records')
    return {r[key]:r if value is None else r[value] for r in rows}

def main():
    import sys
    from scibench.cli import main as cli_main
    return cli_main(['score',*sys.argv[1:]])

if __name__=='__main__':
    raise SystemExit(main())
