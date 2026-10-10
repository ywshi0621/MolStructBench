"""Transport guard, not an agent loop. OpenCode alone chooses/executes tools."""
import hashlib
import copy
import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from runner.thinking_memory import ThinkingMemory, ThinkingAccumulator
from runner.budget import Budget
from runner.provider_adapters import ProviderAdapter
from runner.limiter import provider_slot

def text_content(content):
    if isinstance(content, str): return content
    if isinstance(content, list) and all(x.get('type') == 'text' for x in content):
        return ''.join(x['text'] for x in content)
    raise ValueError('Unexpected content representation')



def prior_tool_call_count(messages):
    count = 0
    for message in messages[2:]:
        if message.get('role') != 'assistant':
            continue
        calls = message.get('tool_calls') or []
        if isinstance(calls, list):
            count += len(calls)
    return count

def normalize_request(body, task, profile, initial_user=None):
    """Rebuild trusted task headers on EVERY request; discard SDK instructions.

    User/developer/system messages from OpenCode have no authority, regardless of
    position or text. Only paired assistant/tool continuation is forwarded.
    """
    continuation=[]
    pending=set(); seen=set()
    for message in body.get('messages',[]):
        role=message.get('role')
        if role in ('system','user','developer'):continue
        if role=='assistant':
            if pending:raise ValueError('Assistant arrived before matching tool results')
            for call in message.get('tool_calls') or []:
                cid=call.get('id')
                if not cid or cid in seen:raise ValueError('Invalid or duplicate tool_call_id')
                if call.get('function',{}).get('name') not in ({'scientific_shell','websearch'} if profile=='B' else {'scientific_shell'}):
                    raise ValueError('Unauthorized continuation tool')
                seen.add(cid);pending.add(cid)
        elif role=='tool':
            cid=message.get('tool_call_id')
            if cid not in pending:raise ValueError('Tool result has no matching assistant call')
            pending.remove(cid)
        else:raise ValueError('Unsupported continuation role')
        continuation.append(copy.deepcopy(message))
    if pending:raise ValueError('Missing tool result')
    body['messages']=copy.deepcopy(task['messages'][:2])+continuation
    allowed=set() if profile=='none' else {'scientific_shell'}
    if profile=='B':allowed.add('websearch')
    if not {t.get('function',{}).get('name') for t in body.get('tools',[])} <= allowed:
        raise ValueError('Unauthorized tool definition')
    if profile=='none' and (body.get('tools') or continuation):raise ValueError('No-tool parity protocol changed')
    return body

def validate_request(body, task, profile):
    """Strict validator used by protocol tests/direct diagnostics."""
    messages = body.get('messages', [])
    if len(messages) < 2:
        raise ValueError('Missing original task')
    for i in range(2):
        if messages[i].get('role') != task['messages'][i]['role'] or text_content(messages[i].get('content')) != task['messages'][i]['content']:
            raise ValueError('Original benchmark prompt changed')
    if any(m.get('role') in ('system','user','developer') for m in messages[2:]):
        raise ValueError('Unexpected injected instruction')
    allowed = set() if profile == 'none' else {'scientific_shell'}
    if profile == 'B': allowed.add('websearch')
    names = {t.get('function', {}).get('name') for t in body.get('tools', [])}
    if not names <= allowed:
        raise ValueError('Unauthorized tool definition')
    if profile == 'none' and (body.get('tools') or len(messages) != 2):
        raise ValueError('No-tool parity protocol changed')

class Gateway:
    def __init__(self, model, runtime, task, profile, key, mock=False):
        self.model, self.runtime, self.task, self.profile = model, runtime, task, profile
        self.key, self.mock = key, mock
        self.token = secrets.token_hex(32)
        self.records = []
        self.status = None
        self.mock_calls = 0
        self.initial_user = None
        self.budget = Budget(runtime)
        self.finalization_answer = None
        self.completed_finalization = threading.Event()
        self.cancelled = threading.Event()
        self.thinking_memory = ThinkingMemory()
        self.provider_adapter = ProviderAdapter(model)
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args): pass
            def reject(self, status, reason):
                data = json.dumps({'error': {'message': reason, 'type': 'harness_error'}}).encode()
                self.send_response(status); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_POST(self):
                if self.path != '/v1/chat/completions' or self.headers.get('Authorization') != 'Bearer '+owner.token:
                    return self.reject(403, 'Unauthorized transport')
                body={}
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length < 8*1024**2: raise ValueError('Invalid payload length')
                    body = json.loads(self.rfile.read(length))
                    if owner.cancelled.is_set() or owner.completed_finalization.is_set():return self.reject(409,'Sample stopped')
                    incoming=body.get('messages',[])
                    repaired=[m.get('role') for m in incoming[:2]]!=['system','user']
                    # Pure canonicalization retry never calls the model or replays tools.
                    for protocol_attempt in range(owner.runtime.get('api_max_attempts',3)):
                        try:
                            normalize_request(body, owner.task, owner.profile)
                            break
                        except ValueError:
                            if protocol_attempt+1==owner.runtime.get('api_max_attempts',3):raise
                            time.sleep(min(2**protocol_attempt,4))
                    body, forced = owner.budget.prepare(body)
                except (ValueError, KeyError, TypeError) as exc:
                    owner.records.append({'rejected': 'invalid_protocol', 'error_class':type(exc).__name__,
                        'reason':str(exc),
                        'roles':[m.get('role') for m in body.get('messages',[])],
                        'tool_names':[t.get('function',{}).get('name') for t in body.get('tools',[])]})
                    owner.status = 'budget_failure' if owner.budget.finalization_calls else 'protocol_rejected'
                    return self.reject(400, 'Benchmark protocol rejected')
                m = owner.model
                body.update(model=m['name'], max_tokens=m['max_tokens'])
                if m.get('temperature') is not None: body['temperature']=m['temperature']
                else: body.pop('temperature',None)
                body['stream']=True
                body['stream_options']={'include_usage':True}
                if m.get('reasoning_effort') is not None:
                    body['reasoning_effort'] = m['reasoning_effort']
                else:
                    body.pop('reasoning_effort', None)
                if m.get('enable_thinking') is not None:
                    body['enable_thinking'] = m['enable_thinking']
                else:
                    body.pop('enable_thinking', None)
                # Qwen 3.8 expects historical reasoning_content in tool continuations.
                # The SDK may omit it; restore only the actual provider deltas, in RAM.
                restored=0
                if m.get('preserve_thinking') is not None:
                    body['preserve_thinking']=m['preserve_thinking']
                else: body.pop('preserve_thinking',None)
                if m.get('restore_reasoning_history',m.get('preserve_thinking',False)):
                    restored=owner.thinking_memory.restore(body['messages'])
                if m.get('reasoning_effort') is not None:
                    body.pop('thinking_budget',None)
                # Discard provider-specific defaults that were not configured.
                for name in ('top_p','top_k','seed','frequency_penalty','presence_penalty'):
                    body.pop(name, None)
                provider_body, endpoint = owner.provider_adapter.prepare(body)
                wire = json.dumps(provider_body, ensure_ascii=False).encode()
                rec = {'request_sha256': hashlib.sha256(wire).hexdigest(),
                       'original_messages_exact': body['messages'][:2]==owner.task['messages'][:2], 'message_count': len(body['messages']),
                       'provider_roles':[x['role'] for x in body['messages']],
                       'runtime_controls_trusted':True, 'soft_budget_triggered':owner.budget.soft_anchor is not None,
                       'forced_finalization_call':forced,
                       'initial_user_order_repaired':repaired,
                       'tool_names': [x['function']['name'] for x in body.get('tools', [])],
                       'temperature': m.get('temperature'), 'reasoning_effort': m.get('reasoning_effort'), 'enable_thinking':m.get('enable_thinking'),
                       'preserve_thinking':m.get('preserve_thinking'), 'reasoning_history_restored_messages':restored}
                owner.records.append(rec)
                if owner.mock:
                    return self.mock_reply(body)
                req = urllib.request.Request(m['base_url'].rstrip('/')+endpoint, wire,
                      {'Authorization': 'Bearer '+owner.key, 'Content-Type': 'application/json'})
                rec['attempts']=[]
                for attempt in range(owner.runtime.get('api_max_attempts',3)):
                    audit={'attempt':attempt+1}; rec['attempts'].append(audit)
                    start=time.monotonic(); retryable=True; lines=[]
                    try:
                        # Buffer one provider response in RAM. A retry never replays
                        # partial content or tool calls into the OpenCode agent.
                        with provider_slot('solver',owner.runtime.get('global_provider_concurrency',9),owner.cancelled.is_set), urllib.request.urlopen(req,timeout=owner.runtime['request_timeout_seconds']) as response:
                            audit['http_status']=response.status; terminal=False; size=0
                            for line in response:
                                if owner.cancelled.is_set():raise TimeoutError('Sample stopped')
                                size+=len(line)
                                if size>16*1024**2: raise ValueError('Provider response size limit')
                                lines.append(line)
                                if line.startswith(b'data:') and line[5:].strip()!=b'[DONE]':
                                    event=json.loads(line[5:].strip())
                                    if event.get('usage'):audit['usage']=event['usage']
                                    if event.get('model'):rec['response_model']=event['model']
                                    if owner.provider_adapter.terminal(event):terminal=True
                            if not terminal: raise OSError('Incomplete provider stream')
                        lines, translated_usage, response_model = owner.provider_adapter.convert(lines)
                        if translated_usage:audit['usage']=translated_usage
                        if response_model:rec['response_model']=response_model
                        rec['transport']=owner.provider_adapter.transport
                        rec['wire_temperature']=provider_body.get('temperature')
                        audit['latency_seconds']=round(time.monotonic()-start,3)
                        audit['status']='success';rec['http_status']=200
                        if audit.get('usage'):rec['provider_usage']=audit['usage']
                        accumulator=ThinkingAccumulator(owner.thinking_memory)
                        if m.get('restore_reasoning_history',m.get('preserve_thinking',False)):
                            for line in lines:
                                if line.startswith(b'data:') and line[5:].strip()!=b'[DONE]':accumulator.accept(json.loads(line[5:].strip()))
                        if forced:
                            parts=[]; illegal_tool=False; stopped=False
                            for line in lines:
                                if not line.startswith(b'data:') or line[5:].strip()==b'[DONE]':continue
                                event=json.loads(line[5:].strip())
                                for choice in event.get('choices',[]):
                                    delta=choice.get('delta',{})
                                    if delta.get('tool_calls'):illegal_tool=True
                                    if isinstance(delta.get('content'),str):parts.append(delta['content'])
                                    if choice.get('finish_reason')=='stop':stopped=True
                            final=''.join(parts).strip()
                            if illegal_tool or not stopped or not final:
                                owner.status='budget_failure';owner.budget.finalization_status='invalid_final'
                                owner.completed_finalization.set()
                                return self.reject(400,'Invalid forced finalization')
                            owner.finalization_answer=final
                            owner.budget.finalization_status='success'
                            owner.completed_finalization.set()
                        self.send_response(200);self.send_header('Content-Type','text/event-stream')
                        self.send_header('Connection','close');self.end_headers()
                        try:
                            for line in lines:self.wfile.write(line)
                            self.wfile.flush()
                        except (BrokenPipeError,ConnectionResetError): pass
                        self.close_connection=True
                        return
                    except urllib.error.HTTPError as exc:
                        audit['http_status']=exc.code;audit['error']='http_'+str(exc.code)
                        retryable=exc.code in (408,429,500,502,503,504)
                    except (OSError,TimeoutError) as exc:
                        audit['error']=type(exc).__name__
                    except (ValueError,KeyError,TypeError) as exc:
                        audit['error']=type(exc).__name__;retryable=False
                    finally:
                        audit['latency_seconds']=round(time.monotonic()-start,3)
                    if owner.cancelled.is_set() or not retryable or attempt+1>=owner.runtime.get('api_max_attempts',3):break
                    time.sleep(min(2**(attempt+1),8))
                owner.status='provider_http_'+str(audit['http_status']) if audit.get('http_status',200)!=200 else 'provider_transport_error'
                rec['http_status']=audit.get('http_status')
                if forced:
                    owner.status='budget_failure';owner.budget.finalization_status='provider_failure'
                    owner.completed_finalization.set()
                self.reject(502,owner.status)
            def mock_reply(self, body):
                owner.mock_calls += 1
                self.send_response(200); self.send_header('Content-Type','text/event-stream')
                self.send_header('Connection','close'); self.end_headers()
                def send(delta, finish=None, usage=None):
                    chunk = {'id':'mock', 'object':'chat.completion.chunk', 'created':1, 'model':owner.model['name'],
                             'choices':[{'index':0,'delta':delta,'finish_reason':finish}]}
                    if usage: chunk['usage'] = usage
                    self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode()); self.wfile.flush()
                send({'role':'assistant'})
                send({'reasoning_content':'MOCK_REASONING_MUST_NOT_BE_SAVED'})
                hard=owner.budget.finalization_calls>0
                keep_loop=owner.runtime.get('mock_tool_rounds',1)>=owner.mock_calls
                if not hard and owner.profile != 'none' and keep_loop:
                    send({'tool_calls':[{'index':0,'id':'call_sci_'+str(owner.mock_calls),'type':'function','function':{
                        'name':'scientific_shell','arguments':json.dumps({'command':'python -c "print(2 + 2)"'})}}]})
                    send({}, 'tool_calls', {'prompt_tokens':10,'completion_tokens':8,'total_tokens':18})
                else:
                    if hard:
                        owner.finalization_answer='MOCK_FINAL_4';owner.budget.finalization_status='success'
                        owner.completed_finalization.set()
                    send({'content':'MOCK_FINAL_4'})
                    send({}, 'stop', {'prompt_tokens':20,'completion_tokens':5,'total_tokens':25})
                self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush(); self.close_connection=True
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    def __enter__(self):
        self.thread.start(); return self
    def __exit__(self, *args):
        self.cancelled.set()
        self.server.shutdown(); self.server.server_close(); self.key = None
        self.thinking_memory.clear()
    @property
    def url(self): return 'http://127.0.0.1:'+str(self.server.server_port)+'/v1'
