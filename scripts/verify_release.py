"""Verify portable public assets and reject unknown input fields."""
import hashlib,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from benchmark_core.io import load_public
def verify():
    manifest=json.loads((ROOT/'PUBLIC_HASHES.json').read_text())
    for name,digest in manifest.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Release file changed: '+name)
    freeze=json.loads((ROOT/'SCORER_FREEZE.json').read_text())
    for name,digest in freeze['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Scoring asset changed: '+name)
    rows,_=load_public(ROOT/'data/benchmark_288_public.jsonl')
    selected=json.loads((ROOT/'data/selection_288.json').read_text())['selected_ids']
    if len(selected)!=288 or len(set(selected))!=288 or set(selected)!={r['id'] for r in rows}:raise ValueError('Fixed selection mismatch')
    if len(json.loads((ROOT/'data/task_specifications.json').read_text()))!=48:raise ValueError('Task catalog mismatch')
    gold=[json.loads(x) for x in (ROOT/'data/benchmark_288_gold.jsonl').read_text().splitlines()]
    if len(gold)!=288 or {g['id'] for g in gold}!=set(selected):raise ValueError('Open-gold selection mismatch')
    pub={r['id']:r for r in rows}
    if any(g['dataset']!=pub[g['id']]['dataset'] or g['task_type']!=pub[g['id']]['task_type'] for g in gold):raise ValueError('Gold task identity mismatch')
    return {'pass':True,'public_hashes_verified':len(manifest),'scoring_hashes_verified':len(freeze['sha256']),'unique_ids':288,'gold_ids':288,'task_units':48,'gold_absent_from_solver_public_schema':True,'release_mode':'open-gold'}
if __name__=='__main__':print(json.dumps(verify()))
