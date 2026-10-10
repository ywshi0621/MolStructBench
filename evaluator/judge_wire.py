"""One byte-exact request serializer and immutable public-evidence snapshot."""
import copy,functools,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def request_body(payload,config,prompt):
    body={'model':config['model'],'messages':[{'role':'system','content':prompt},
          {'role':'user','content':json.dumps(payload,ensure_ascii=False,sort_keys=True)}],
          'temperature':config['temperature'],'max_tokens':config['max_tokens'],'stream':True,
          'stream_options':{'include_usage':True},'response_format':{'type':'json_object'}}
    for field in ('enable_thinking','reasoning_effort'):
        if config.get(field) is not None:body[field]=config[field]
    return body

def request_bytes(payload,config,prompt):
    return json.dumps(request_body(payload,config,prompt),ensure_ascii=False).encode('utf-8')

@functools.lru_cache(maxsize=1)
def evidence_snapshot():
    path=ROOT/'data/public_evidence_v1.jsonl'
    freeze=json.loads((ROOT/'SCORER_FREEZE.json').read_text(encoding='utf-8'))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=freeze['sha256']['data/public_evidence_v1.jsonl']:
        raise ValueError('Frozen public evidence snapshot changed')
    rows=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    if len(rows)!=288 or len({r['id'] for r in rows})!=288:raise ValueError('Invalid evidence snapshot')
    return {r['id']:r for r in rows}

def frozen_evidence(task):
    row=evidence_snapshot().get(task['id'])
    question=task['messages'][1]['content']
    if row is None or row['question_sha256']!=hashlib.sha256(question.encode('utf-8')).hexdigest():
        raise ValueError('Evidence snapshot does not match frozen public question')
    return copy.deepcopy(row['evidence'])
