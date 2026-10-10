"""Gold-independent final-region extraction and structured answer parsing.

An explicit final heading supersedes preceding analysis. All assertions inside
that final region remain visible; selecting a matching answer from gold is forbidden.
"""
import json
import re
import unicodedata

FINAL = re.compile(r'(?im)^\s*(?:#{1,6}\s*|\*\*)?(?:final\s+(?:answer|result|conclusion)|answer|conclusion|result|output|最终(?:答案|结果|结论)|答案|结果|输出|结论|结果汇总)(?:\*\*)?\s*(?:[:：]\s*|$)')

def final_region(text):
    text = unicodedata.normalize('NFKC', text or '').replace('−', '-')
    matches=list(FINAL.finditer(text))
    # A specifically marked final answer supersedes preliminary results.  If
    # multiple ordinary answer sections occur, retain all of them so a later
    # contradictory claim is not silently selected.
    explicit=[m for m in matches if re.search(r'(?i)final|最终',m.group(0))]
    # Keep every assertion after the first final heading. A later repeated
    # heading cannot erase a contradictory final answer already stated.
    start=(explicit[0] if explicit else matches[0]) if matches else None
    return text[start.end():].strip() if start else text.strip()

def json_values(text):
    decoder = json.JSONDecoder(object_pairs_hook=unique_keys)
    values = []
    pos = 0
    while pos < len(text):
        if text[pos] not in '[{':
            pos += 1; continue
        try:
            value, end = decoder.raw_decode(text[pos:])
        except (ValueError, TypeError):
            pos += 1; continue
        values.append(value); pos += end
    return values

def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result and result[key] != value:
            raise ValueError('Conflicting duplicate JSON keys')
        result[key] = value
    return result

def fields(value, names):
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            k = re.sub(r'[\s_-]', '', key).lower()
            if k in names: result.append(item)
            elif isinstance(item, (dict, list)): result.extend(fields(item, names))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)): result.extend(fields(item, names))
    return result

def unique(values):
    result = []
    for value in values:
        if value not in result: result.append(value)
    return result

def int_list(value):
    return isinstance(value, list) and all(type(x) is int for x in value)

def index_candidates(text, keys=('atomindices','atomindex','indices','原子索引')):
    result = []
    for value in json_values(text):
        candidates = fields(value, set(keys)) if isinstance(value, dict) else [value]
        for candidate in candidates:
            if type(candidate) is int: result.append([candidate])
            elif int_list(candidate): result.append(candidate)
    # Include prose assertions too, so contradictory JSON/prose cannot be hidden.
    plain = re.sub(r'[*`_"\']', '', text)
    for m in re.finditer(r'(?:atom\s*(?:indices|index)|原子索引|端点原子)\s*[:：=|]?\s*(\[[\d,\s-]+\]|-?\d+(?:\s*,\s*-?\d+)*)', plain, re.I):
        result.append([int(x) for x in re.findall(r'-?\d+', m.group(1))])
    return unique([sorted(set(x)) for x in result])

def group_values(text):
    result = []
    for value in json_values(text):
        candidates = fields(value, {'matches','groups','substituentgroups','atomindices','atomgroups'}) if isinstance(value, dict) else [value]
        for x in candidates:
            if int_list(x): result.append(x)
            elif isinstance(x, list) and all(int_list(a) for a in x): result.extend(x)
    return unique([sorted(set(x)) for x in result])

def answer_line(text):
    """Use an unambiguous terminal one-line answer after prose, if present."""
    lines=[re.sub(r'^[>*\s`-]+|[\s`*]+$', '',x) for x in text.splitlines()]
    lines=[x for x in lines if x]
    terse=r'[ABab]|[+-]?\d+|\[[\d,\s-]+\]|close_analog|related_analog|not_close_analog|present|absent|yes|no'
    if len(lines)>1 and re.fullmatch(terse,lines[-1],re.I):
        if any(re.fullmatch(terse,line,re.I) for line in lines[:-1]): return text
        return lines[-1]
    if len(lines)>1 and re.fullmatch(terse,lines[0],re.I): return lines[0]
    return text

def dedup_boxes(boxes):
    # Repeated prose rounded to three decimals is equivalent to the original.
    # Never use the gold's 0.01-A scoring tolerance to erase distinct predictions.
    result = []
    for box in boxes:
        if not any(max(abs(a-b) for a,b in zip(box, old)) <= 0.000501 for old in result): result.append(box)
    return result
