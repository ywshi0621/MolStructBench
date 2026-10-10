"""Read only the exact public JSONL member; never extract a whole archive."""
import hashlib
import json
import random
import re
import zipfile
from collections import defaultdict
from pathlib import Path

FIELDS = {'id', 'dataset', 'task_type', 'lang', 'input_representation', 'messages'}
DATASETS = {'3d_0907': 'Native 3D', '3d_to_2d_v7_5_final': '3D to 2D',
 'pure2d_full_rdkit2024035_sft_v4_pairwisefix_groundingaligned_v12_20260824': 'Pure2D'}

def digest(value):
    return hashlib.sha256(value).hexdigest()

def prompt_hash(messages):
    return digest(json.dumps(messages, ensure_ascii=False, separators=(',', ':')).encode())

def validate_row(row):
    if set(row) not in (FIELDS, FIELDS | {'subtask'}):
        raise ValueError('Unexpected public schema; refusing unknown metadata')
    if not re.fullmatch(r'scibench_\d{6}', row['id']):
        raise ValueError('Invalid public sample ID')
    if row['dataset'] not in DATASETS:
        raise ValueError('Unknown dataset')
    messages = row['messages']
    if len(messages) != 2 or [m['role'] for m in messages] != ['system', 'user']:
        raise ValueError('Expected the original two-message contract')
    if any(set(m) != {'role', 'content'} or not isinstance(m['content'], str) for m in messages):
        raise ValueError('Unexpected message schema')
    return row

def load_public(path):
    path=Path(path)
    if path.suffix=='.jsonl': raw=path.read_bytes()
    else:
        with zipfile.ZipFile(path) as archive:
            members=[n for n in archive.namelist() if n.endswith('/benchmark_288_public.jsonl') or n=='benchmark_288_public.jsonl']
            if len(members)!=1:raise ValueError('Expected one Core-288 public member')
            raw=archive.read(members[0])
    rows=[validate_row(json.loads(line)) for line in raw.splitlines() if line.strip()]
    units=defaultdict(int)
    for r in rows:units[(r['dataset'],r['task_type'])]+=1
    if len(rows)!=288 or len({r['id'] for r in rows})!=288 or len(units)!=48 or set(units.values())!={6}:raise ValueError('Expected Core-288 / 48 units / 6 each')
    return rows,{'public_jsonl_sha256':digest(raw),'sample_count':288,'task_units':48}
