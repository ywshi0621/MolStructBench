#!/usr/bin/env python3
import argparse, json, re, unicodedata, math
from pathlib import Path
from collections import defaultdict, Counter
from rdkit import Chem
try:
    from evaluator.final_answer import FINAL, final_region, json_values, fields, unique, index_candidates, group_values, dedup_boxes, answer_line
except ImportError:
    from final_answer import FINAL, final_region, json_values, fields, unique, index_candidates, group_values, dedup_boxes, answer_line

ROOT=Path(__file__).resolve().parent
DEFAULT_GOLD=str(ROOT.parent/'data/benchmark_288_gold.jsonl')
DEFAULT_PUBLIC=str(ROOT.parent/'data/benchmark_288_public.jsonl')

def norm(s):
    s=unicodedata.normalize('NFKC',s or '').casefold()
    s=s.translate(str.maketrans({'：':':','；':';','，':',','。':'.','（':'(', '）':')'}))
    return re.sub(r'\s+',' ',s).strip().strip(' .;,:`"\'')

def ints(s):
    return [int(x) for x in re.findall(r'(?<![\d.])-?\d+(?!\d)',s or '')]

def flat_int_lists(s):
    out=[]
    for m in re.finditer(r'\[\s*(-?\d+(?:\s*,\s*-?\d+)*)\s*\]',s or ''):
        out.append([int(x.strip()) for x in m.group(1).split(',')])
    return out

def multiset_of_sets(groups): return Counter(tuple(sorted(set(x))) for x in groups)

def gold_atom_indices(g):
    sg=g.get('structured_grounding') or {}
    return sg.get('atom_indices') or sg.get('scaffold_atom_indices') or []

def gold_groups(g):
    sg=g.get('structured_grounding') or {}
    if sg.get('matches') is not None: return sg['matches']
    if sg.get('substituent_groups') is not None: return sg['substituent_groups']
    ai=sg.get('atom_indices'); return [ai] if ai else []

def explicit_atom_indices(s):
    """Prefer a declared final atom-index answer over integers in reasoning."""
    plain=re.sub(r'[*_`]+','',s or '')
    pat=re.compile(
        r'(?:atom\s+(?:index|indices)|原子索引)\s*[:：]?\s*'
        r'(\[\s*-?\d+(?:\s*,\s*-?\d+)*\s*\]|-?\d+)',
        re.I,
    )
    matches=list(pat.finditer(plain))
    if matches: return ints(matches[-1].group(1))
    lists=flat_int_lists(plain)
    if lists: return lists[-1]
    return ints(plain)

def score_atom_set(pred,g):
    if not FINAL.search(pred):pred=answer_line(pred)
    candidates=index_candidates(pred)
    if not candidates: candidates=[explicit_atom_indices(pred)]
    return float(bool(candidates) and all(set(x)==set(gold_atom_indices(g)) for x in candidates))

def score_atom_groups(pred,g):
    got=group_values(pred) or unique(flat_int_lists(pred))
    if not got and ints(pred): got=[ints(pred)]
    return float(multiset_of_sets(got)==multiset_of_sets(gold_groups(g)))

def score_bond_endpoint(pred,g):
    sg=g.get('structured_grounding') or {}; target=set(sg.get('atom_indices') or [])
    candidates=index_candidates(pred) or flat_int_lists(pred)
    return float(bool(candidates) and all(set(x)==target for x in candidates))

def score_bond_target(pred,g):
    sg=g.get('structured_grounding') or {}; tb=sg.get('target_bond') or {}
    target_pair={tb.get('atom_i'),tb.get('atom_j')}; target_bond=tb.get('bond_index')
    pairs=index_candidates(pred) or flat_int_lists(pred)
    bonds=[]
    for value in json_values(pred): bonds+=fields(value, {'bondindex','bondidx','键索引'})
    plain=re.sub(r'[*_`"\']','',pred)
    bonds += [int(x) for x in re.findall(r'(?:bond\s*index|键索引)\s*(?:[:：=|]\s*)?(\d+)',plain,re.I)]
    return float(bool(pairs) and bool(bonds) and all(set(x)==target_pair for x in pairs) and all(x==target_bond for x in bonds))

def score_scaffold_plus_groups(pred,g):
    sg=g.get('structured_grounding') or {}
    target_scaf=set(sg.get('scaffold_atom_indices') or [])
    target_groups=multiset_of_sets(sg.get('substituent_groups') or [])
    structured=[]
    for value in json_values(pred):
        if not isinstance(value,dict):continue
        scaffolds=fields(value,{'scaffoldatomindices','scaffoldindices','scaffold','骨架原子索引'})
        groups=fields(value,{'substituentgroups','substituents','取代基'})
        if scaffolds and groups:
            structured.extend(float(isinstance(s,list) and set(s)==target_scaf and isinstance(groups_value,list)
                                     and multiset_of_sets(unique(groups_value))==target_groups)
                              for s in scaffolds for groups_value in groups)
    if structured:
        # Structured assertions are all checked; conflicting JSON sections
        # cannot be selected by matching the gold.
        if not all(structured):return 0.0
        decoder=json.JSONDecoder();prose=pred;spans=[];pos=0
        while pos<len(pred):
            if pred[pos]!='{':pos+=1;continue
            try:value,end=decoder.raw_decode(pred[pos:])
            except ValueError:pos+=1;continue
            spans.append((pos,pos+end));pos+=end
        for start,end in reversed(spans):prose=prose[:start]+' '*(end-start)+prose[end:]
        for line in prose.splitlines():
            lists=flat_int_lists(line)
            if not lists:continue
            if re.search(r'scaffold|骨架',line,re.I) and any(set(x)!=target_scaf for x in lists):return 0.0
            if re.search(r'substituent\s*groups|取代基',line,re.I) and multiset_of_sets(unique(lists))!=target_groups:return 0.0
            if any(set(x)!=target_scaf and tuple(sorted(set(x))) not in target_groups for x in lists):return 0.0
        return 1.0
    plain=re.sub(r'[*`_]+','',pred)
    lines=plain.splitlines();scaffold=None;group_starts=[]
    for i,line in enumerate(lines):
        low=line.casefold()
        if (scaffold is None and re.search(r'\bscaffold\b|骨架原子索引|^\s*骨架\s*:',low) and 'smiles' not in low and 'outside' not in low):
            for j in range(i,min(len(lines),i+5)):
                ls=flat_int_lists(lines[j])
                if ls:scaffold=ls[0];break
        if ('取代基' in line or 'substituent groups' in low or re.search(r'\bsubstituents\b',low)) and not re.search(r'\bsubstituent\s*\d+',low):
            group_starts.append(i)
    if scaffold is None:
        ls=flat_int_lists(plain);scaffold=ls[0] if ls else None
    if group_starts:
        start=group_starts[-1] if any('汇总' in lines[i] or 'summary' in lines[i].casefold() for i in group_starts) else group_starts[0]
        groups=unique(flat_int_lists('\n'.join(lines[start:])))
    else:
        groups=unique(flat_int_lists(plain))
    groups=[x for x in groups if set(x)!=set(scaffold or [])]
    return float(scaffold is not None and set(scaffold)==target_scaf and multiset_of_sets(groups)==target_groups)

def property_categories(text):
    aliases={'低':'low','中等':'moderate','偏高':'elevated','高':'high',
             'low':'low','moderate':'moderate','elevated':'elevated','high':'high','intermediate':'moderate'}
    result={'tpsa':[],'clogp':[]}
    for key in result:
        for value in json_values(text):
            for item in fields(value,{key}):
                if isinstance(item,str):result[key].append(aliases.get(norm(item)))
        label='TPSA' if key=='tpsa' else r'c\s*Log\s*P'
        pattern=label+r'\s*(?:[:：=|]\s*)('+ '|'.join(sorted(aliases,key=len,reverse=True))+r')(?=$|[\s.;,。；，|])'
        result[key].extend(aliases[m.group(1).casefold()] for m in re.finditer(pattern,text,re.I))
    columns=None
    for line in text.splitlines():
        if '|' not in line:columns=None;continue
        cells=[norm(c) for c in line.strip().strip('|').split('|')]
        if all(key in cells for key in result):columns={key:cells.index(key) for key in result};continue
        if columns and all(col<len(cells) and cells[col] in aliases for col in columns.values()):
            for key,col in columns.items():result[key].append(aliases[cells[col]])
    return result

def extract_smiles(pred):
    p=(pred or '').strip().strip('`').strip()
    p=re.sub(r'^(?:parent\s+smiles|smiles|母体\s*smiles)\s*[:：]\s*','',p,flags=re.I).strip(' .;')
    if Chem.MolFromSmiles(p): return p
    cands=sorted(re.findall(r'[A-Za-z0-9@+\-\[\]\(\)=#$\\/%.:*]+',p),key=len,reverse=True)
    for c in cands:
        if Chem.MolFromSmiles(c): return c
    return None

def score_smiles(pred,g):
    candidates=[]
    for value in json_values(pred):candidates+=fields(value,{'smiles','parentsmiles','canonicalsmiles'})
    token=r'[A-Za-z0-9@+\-\[\]\(\)=#$\\/%.:*]+'
    candidates+=re.findall(r'(?:parent\s+smiles|smiles|母体\s*smiles)\s*[:：=]\s*('+token+')',pred,re.I)
    candidates+=re.findall(r'(?:parent(?:\s+molecule)?\s+is|母体为)\s*('+token+')',pred,re.I)
    for line in pred.splitlines():
        clean=line.strip().strip('`*').strip()
        if re.fullmatch(token,clean) and not clean.lower() in ('smiles','json'):candidates.append(clean)
    gs=g.get('target_parent_smiles');gm=Chem.MolFromSmiles(gs) if gs else None
    if gm is None or not candidates:return 0.0
    target=Chem.MolToSmiles(gm,canonical=True,isomericSmiles=True)
    for candidate in candidates:
        pm=Chem.MolFromSmiles(candidate.rstrip('.')) if isinstance(candidate,str) else None
        if pm is None or Chem.MolToSmiles(pm,canonical=True,isomericSmiles=True)!=target:return 0.0
    return 1.0

def score_accepted_name(pred,g):
    p=norm(pred).strip('*`')
    p=re.sub(r'^(?:molecule(?: name)?|compound(?: name)?|name|分子名称|化合物名称|名称)\s*[:：]\s*','',p)
    accepted={norm(name) for name in g.get('accepted_names',[])}
    if p in accepted: return 1.0
    # Bilingual name annotations: the Latin name must be an exact accepted name,
    # not a substring of an unrelated name or a choice among alternatives.
    if re.search(r'\b(?:or|not|instead)\b|不是|并非|或者|而非',p): return 0.0
    parts=[norm(x) for x in re.split(r'[()（）]',p) if norm(x)]
    if parts and all(x in accepted for x in parts):return 1.0
    cache_file=ROOT/'name_identity_cache.json'
    if cache_file.exists():
        cache=json.loads(cache_file.read_text(encoding='utf-8'))
        preferred=g.get('preferred_name') or g.get('reference_answer')
        target=cache.get('preferred_to_inchikey',{}).get(preferred)
        name_keys=cache.get('name_to_inchikey',{})
        if target:
            if p in name_keys:return float(name_keys[p]==target)
            found=[name_keys.get(x) for x in parts]
            if found and all(found):return float(all(x==target for x in found))
            if any(key and key!=target for key in found):return 0.0
            if all(x in accepted or name_keys.get(x)==target for x in parts):return 1.0
    # Names that are not in the finite accepted-name list require independent
    # identity verification.  Defer to the anonymous semantic judge, never
    # guess equivalence from a substring or silently mark them incorrect.
    return None if p else 0.0

def score_conformer_choice(pred,g):
    standalone=re.findall(r'(?im)^\s*([ab])\s*$',pred)
    if len(set(x.upper() for x in standalone))>1:return 0.0
    p=norm(answer_line(pred))
    if re.search(r'\b[ab]\s*(?:or|/|或|或者)\s*[ab]\b',p,re.I):return 0.0
    # Prefer explicit 'conformer/构象 A/B'.
    choices=re.findall(r'(?:conformer|构象)\s*([ab])\b',p,re.I)
    m=re.search(r'(?:conformer|构象)\s*([ab])\b',p,re.I)
    if not m:
        m=re.search(r'\b([ab])\b',p,re.I)
    got=m.group(1).upper() if m else None
    if len(set(x.upper() for x in choices))>1:return 0.0
    ref=norm(g.get('reference_answer'))
    mr=re.search(r'(?:conformer|构象)\s*([ab])\b',ref,re.I)
    target=mr.group(1).upper() if mr else None
    return float(got is not None and got==target)

def parse_boxes(s):
    # Only accept bracketed six-number arrays, avoiding atom-index groups.
    num=r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
    pat=re.compile(r'\[\s*('+num+r')\s*,\s*('+num+r')\s*,\s*('+num+r')\s*,\s*('+num+r')\s*,\s*('+num+r')\s*,\s*('+num+r')\s*\]')
    out=[[float(x) for x in m.groups()] for m in pat.finditer(s or '')]
    # Also accept the equivalent axis-pair layout:
    # [[xmin,xmax],[ymin,ymax],[zmin,zmax]].
    nested=re.compile(
        r'\[\s*\[\s*('+num+r')\s*,\s*('+num+r')\s*\]\s*,\s*'
        r'\[\s*('+num+r')\s*,\s*('+num+r')\s*\]\s*,\s*'
        r'\[\s*('+num+r')\s*,\s*('+num+r')\s*\]\s*\]'
    )
    for m in nested.finditer(s or ''):
        xmin,xmax,ymin,ymax,zmin,zmax=map(float,m.groups())
        out.append([xmin,ymin,zmin,xmax,ymax,zmax])
    out.extend(box for box,_ in parse_box_table_rows(s))
    axes=('xmin','ymin','zmin','xmax','ymax','zmax')
    def objects(value):
        if isinstance(value,dict):
            normalized={re.sub(r'[\s_-]','',key).lower():item for key,item in value.items()}
            if all(key in normalized and type(normalized[key]) in (int,float) for key in axes):
                out.append([float(normalized[key]) for key in axes])
            for item in value.values():objects(item)
        elif isinstance(value,list):
            for item in value:objects(item)
    for value in json_values(s):objects(value)
    return out

def parse_box_table_rows(text):
    axes=('xmin','ymin','zmin','xmax','ymax','zmax');columns=None;out=[]
    for line in text.splitlines():
        if '|' not in line:columns=None;continue
        cells=[cell.strip().strip('`*') for cell in line.strip().strip('|').split('|')]
        names=[re.sub(r'[\s_-]','',cell).lower() for cell in cells]
        if all(axis in names for axis in axes):
            columns=[names.index(axis) for axis in axes];continue
        if columns is None or max(columns)>=len(cells):continue
        try:box=[float(cells[col]) for col in columns]
        except ValueError:continue
        if all(math.isfinite(x) for x in box):out.append((box,' '.join(cells)))
    return out

def score_boxes(pred,g,tol=0.01,need_cip=False):
    target=g.get('target_boxes') or []
    # A conditional aside describing an optional *different* requested box
    # is not an additional final box assertion.
    relevant='\n'.join(line for line in pred.splitlines() if not re.search(r'^\s*[（(]\s*(?:若需|if\s+(?:needed|required))',line,re.I))
    got=dedup_boxes(parse_boxes(relevant))
    if len(got)!=len(target): return 0.0, {'box_count_match':False,'max_abs_error':None}
    def max_error(boxes_a,boxes_b):
        errs=[]
        for a,b in zip(boxes_a,boxes_b): errs += [abs(float(x)-float(y)) for x,y in zip(a,b)]
        return max(errs) if errs else 0.0
    maxerr=max_error(got,target)
    ok=maxerr<=tol
    match_mode='gold_box' if ok else None
    cip_ok=True
    if need_cip:
        target_cip=[str(x).upper() for x in (g.get('target_cip_labels') or [])]
        # Capture standalone R/S in occurrence order.
        # CIP labels belong to the final box assertions, not explanatory
        # comparisons of candidate R/S assignments elsewhere in the answer.
        lines=relevant.splitlines(); pairs=[]
        for i,line in enumerate(lines):
            for box in parse_boxes(line):
                # Prefer a label on the box row; otherwise use the nearest
                # preceding heading/row, stopping at the previous box.
                context=line
                if not re.search(r'(?<![A-Za-z])([RS])(?![A-Za-z])',context):
                    for j in range(i-1,max(-1,i-7),-1):
                        if parse_boxes(lines[j]):break
                        context+=' '+lines[j]
                        if re.search(r'(?<![A-Za-z])([RS])(?![A-Za-z])',lines[j]):break
                labels=re.findall(r'(?<![A-Za-z])([RS])(?![A-Za-z])',context)
                pairs.append((box,labels[0].upper() if len(set(x.upper() for x in labels))==1 else None))
        for box,context in parse_box_table_rows(relevant):
            labels=re.findall(r'(?<![A-Za-z])([RS])(?![A-Za-z])',context)
            pairs.append((box,labels[0] if len(set(labels))==1 else None))
        distinct=[]
        for box,label in pairs:
            if not any(max(abs(a-b) for a,b in zip(box,old))<=0.000501 and label==old_label for old,old_label in distinct):
                distinct.append((box,label))
        got_cip=[label for _,label in distinct]
        if len(got_cip)!=len(got):got_cip=[]
        explicit=[x.upper() for x in re.findall(r'\bCIP\s*[:=]\s*([RS])\b',pred,re.I)]
        if explicit and any(x not in target_cip for x in explicit):got_cip=[]
        if got and len(got_cip)>len(got) and len(got_cip)%len(got)==0:
            chunks=[got_cip[i:i+len(got)] for i in range(0,len(got_cip),len(got))]
            if all(chunk==chunks[0] for chunk in chunks): got_cip=chunks[0]
        cip_ok=(got_cip==target_cip)
        ok=ok and cip_ok
    return float(ok), {'box_count_match':True,'max_abs_error':maxerr,'cip_match':cip_ok,'box_match_mode':match_mode}

def _deterministic_score(pred,g):
    pred=final_region(pred)
    mt=g['metric_type']
    if mt=='normalized_exact':
        if 'tpsa' in norm(g.get('reference_answer')) and 'clogp' in norm(g.get('reference_answer')):
            target=property_categories(g['reference_answer']);got=property_categories(pred)
            return float(all(got[key] and target[key] and all(x==target[key][0] for x in got[key]) for key in target)),{}
        candidates=[]
        for value in json_values(pred): candidates+=fields(value, {'answer','label','result','classification'})
        if not candidates: candidates=[re.sub(r'^(?:answer|label|classification|答案|分类)\s*[:：]\s*','',answer_line(pred).strip('*` \n'),flags=re.I)]
        target=norm(g.get('reference_answer'))
        def matches(x):
            if not isinstance(x,str):return False
            nx=norm(x)
            if nx==target:return True
            # A required categorical label can be followed by an explanation;
            # a contradictory alternative label still fails.
            if not re.fullmatch(r'[\w\u3400-\u9fff.+-]+',target):return False
            if not re.match(r'^'+re.escape(target)+r'(?=$|[\s:;,.，。；：()])',nx):return False
            opposites={'present':'absent','absent':'present','yes':'no','no':'yes',
                       'close_analog':'related_analog|not_close_analog',
                       'related_analog':'close_analog|not_close_analog',
                       'not_close_analog':'close_analog|related_analog'}
            other=opposites.get(target)
            return not(other and re.search(r'(?<![\w])(?:'+other+r')(?![\w])',nx[len(target):]))
        return float(bool(candidates) and all(matches(x) for x in candidates)),{}
    if mt=='atom_set_exact': return score_atom_set(pred,g),{}
    if mt=='atom_group_set_exact': return score_atom_groups(pred,g),{}
    if mt=='bond_endpoint_exact': return score_bond_endpoint(pred,g),{}
    if mt=='bond_target_exact': return score_bond_target(pred,g),{}
    if mt=='scaffold_plus_groups_exact': return score_scaffold_plus_groups(pred,g),{}
    if mt=='canonical_smiles_exact': return score_smiles(pred,g),{}
    if mt=='accepted_name_exact': return score_accepted_name(pred,g),{}
    if mt=='conformer_choice': return score_conformer_choice(pred,g),{}
    if mt=='ordered_box3d_tol_0.01A': return score_boxes(pred,g,0.01,False)
    if mt=='ordered_box3d_plus_cip': return score_boxes(pred,g,0.01,True)
    return None,{}

def deterministic_score(pred,g):
    final=final_region(pred)
    score,diagnostics=_deterministic_score(pred,g)
    diagnostics=dict(diagnostics)
    diagnostics['final_region_extracted']=(final!=(pred or '').strip())
    diagnostics['parser_failure']=False
    metric=g['metric_type']
    if final and score is not None:
        if metric.startswith('ordered_box'): diagnostics['parser_failure']=not bool(parse_boxes(final))
        elif metric in ('atom_set_exact','atom_group_set_exact','bond_endpoint_exact','bond_target_exact','scaffold_plus_groups_exact'):
            diagnostics['parser_failure']=not bool(ints(final))
    return score,diagnostics

def loadj(path):
    with open(path,encoding='utf-8') as f: return [json.loads(x) for x in f if x.strip()]

def aggregate(rows):
    by_task=defaultdict(list)
    for r in rows:
        if r.get('score') is not None: by_task[(r['dataset'],r['task_type'])].append(float(r['score']))
    task_scores={f'{ds}::{task}':sum(v)/len(v) for (ds,task),v in sorted(by_task.items())}
    by_ds=defaultdict(list)
    for key,score in task_scores.items(): by_ds[key.split('::',1)[0]].append(score)
    ds_macro={ds:sum(v)/len(v) for ds,v in sorted(by_ds.items())}
    overall=(sum(ds_macro.values())/len(ds_macro)) if ds_macro else None
    return task_scores,ds_macro,overall

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--predictions',required=True)
    ap.add_argument('--gold',default=DEFAULT_GOLD)
    ap.add_argument('--public',default=DEFAULT_PUBLIC)
    ap.add_argument('--judge-scores',default=None,help='Optional JSONL: {"id":"...","score":0|1|2}; scores are divided by 2.')
    ap.add_argument('--out',default=str(ROOT/'eval_results.json'))
    ap.add_argument('--judge-queue',default=str(ROOT/'semantic_judge_queue.jsonl'))
    args=ap.parse_args()
    gold={x['id']:x for x in loadj(args.gold)}; pub={x['id']:x for x in loadj(args.public)}
    preds={x['id']:x.get('prediction','') for x in loadj(args.predictions)}
    judge_scores={}
    if args.judge_scores:
        for x in loadj(args.judge_scores): judge_scores[x['id']]=float(x['score'])/2.0
    missing=sorted(set(gold)-set(preds)); extra=sorted(set(preds)-set(gold))
    rows=[]; judge=[]
    for id_,g in gold.items():
        if id_ not in preds: continue
        pred=preds[id_]; sc,diag=deterministic_score(pred,g)
        if sc is None and id_ in judge_scores: sc=judge_scores[id_]
        rec={'id':id_,'dataset':g['dataset'],'task_type':g['task_type'],'metric_type':g['metric_type'],'score':sc,**diag}
        rows.append(rec)
        if sc is None:
            judge.append({
                'id':id_,'dataset':g['dataset'],'task_type':g['task_type'],
                'question_and_input':pub[id_]['messages'][1]['content'],'prediction':pred,
                'reference_answer':g.get('reference_answer'),'private_facts':g.get('private_facts_for_judging'),
                'judge_instruction':(
                    'Score factual task completion only. Return JSON {"score":0|1|2,"reason":"..."}. '
                    '2 = all essential requested facts are correct with no material contradiction; '
                    '1 = partially correct but missing or misstating some required content; '
                    '0 = substantially incorrect or fails the requested task. Do not reward style or verbosity.'
                )
            })
    with open(args.judge_queue,'w',encoding='utf-8') as f:
        for x in judge: f.write(json.dumps(x,ensure_ascii=False)+'\n')
    scored=[r for r in rows if r['score'] is not None]
    task_scores,ds_macro,overall=aggregate(scored)
    out={
        'prediction_count':len(preds),'matched_count':len(rows),'missing_ids':missing,'extra_ids':extra,
        'scored_count':len(scored),'semantic_judge_pending_count':len(judge),
        'task_scores':task_scores,'dataset_macro_scores':ds_macro,
        'overall_equal_dataset_macro':overall,
        'aggregation':'mean samples within dataset×task; mean task scores within each dataset; overall = equal mean of the three dataset macro scores',
        'box_metric':'ordered box arrays; all six coordinates per box must be within 0.01 angstrom; stereocenter task also requires ordered CIP R/S labels',
    }
    Path(args.out).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
