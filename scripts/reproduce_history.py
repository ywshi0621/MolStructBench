"""Run the public local scorer on all five archived answers, never a Solver."""
import argparse,hashlib,inspect,json,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluator.official_scorer import aggregate,score_rows,median_three
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True)
    migration=json.loads((ROOT/'docs/HASH_MIGRATION.json').read_text())
    for fn in (aggregate,score_rows,median_three):assert hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()==migration['frozen_scoring_function_sha256'][fn.__name__]
    history=ROOT/'examples/history';index=json.loads((history/'INDEX.json').read_text());report=[];changes=[]
    for entry in index['runs']:
        run=history/entry['key'];dest=out/entry['key']
        process=subprocess.run([sys.executable,'-m','scibench.cli','score','--predictions',str(run/'predictions.jsonl'),'--output',str(dest),'--offline'],capture_output=True,text=True,cwd=ROOT)
        if process.returncode:raise RuntimeError('Local archived scoring failed: '+process.stderr)
        result=json.loads((dest/'final_results.json').read_text());expected=json.loads((run/'expected_final_results.json').read_text())
        current={r['id']:r for r in map(json.loads,(dest/'per_sample_scores.jsonl').read_text().splitlines())};previous={r['id']:r for r in map(json.loads,(run/'expected_per_sample_scores.jsonl').read_text().splitlines())}
        assert len(current)==288 and set(current)==set(previous)
        for sid,row in current.items():
            if row['score']!=previous[sid]['score'] or row['stage']!=previous[sid]['stage']:changes.append({'model_key':entry['key'],'id':sid,'old':previous[sid],'new':row})
        for field in ('overall_score','official_v1_score','dataset_breakdown','task_breakdown','deterministic_score','semantic_score','micro_score','pending_count'):assert result[field]==expected[field],(entry['key'],field)
        assert result['judge_statistics']['completed_calls']==entry['vote_count'] and result['judge_statistics']['new_calls_this_invocation']==0
        before=(dest/'semantic_stage/judge_triples.jsonl').read_bytes()
        resumed=subprocess.run([sys.executable,'-m','scibench.cli','score','--predictions',str(run/'predictions.jsonl'),'--output',str(dest),'--offline','--resume'],capture_output=True,text=True,cwd=ROOT)
        assert resumed.returncode==0 and before==(dest/'semantic_stage/judge_triples.jsonl').read_bytes()
        report.append({'model_key':entry['key'],'official_score':result['official_v1_score'],'samples':288,'task_units':len(result['task_breakdown']),'judge_votes':entry['vote_count'],'pending':0,'resume_passed':True,'new_api_calls':0})
        print(json.dumps(report[-1]),flush=True)
    assert not changes,changes
    summary={'pass':True,'runs':report,'predictions':1440,'judge_votes':sum(r['judge_votes'] for r in report),'per_sample_score_changes':changes,'new_solver_calls':0,'new_judge_calls':0,'scoring_functions_unchanged':True}
    (out/'REPRODUCTION_REPORT.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
