"""Core-only deterministic gold self-test; no model/API calls."""
import json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluator.deterministic_r2 import deterministic_score
def main():
    rows=[json.loads(x) for x in (ROOT/'data/benchmark_288_gold.jsonl').read_text().splitlines()]
    deterministic=[r for r in rows if r['metric_type']!='semantic_judge']
    failures=[r['id'] for r in deterministic if deterministic_score(r['reference_answer'],r)[0]!=1]
    assert len(deterministic)==180 and not failures,failures
    print(json.dumps({'pass':True,'passed':180,'total':180,'new_api_calls':0}))
if __name__=='__main__':main()
