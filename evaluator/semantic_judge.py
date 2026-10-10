"""Local evaluation stage only; never imported by Solver tools or prompts."""
import datetime,hashlib,json,os,time,urllib.error,urllib.request
from pathlib import Path
import yaml
from benchmark_core.io import digest
from benchmark_core.limiter import provider_slot
from evaluator.judge_wire import request_bytes,frozen_evidence
ROOT=Path(__file__).resolve().parents[1]
def utc_now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def judge_input(task, gold, specs, prediction):
    spec_key=task['dataset']+'::'+task['task_type']+('::'+task['subtask'] if task.get('subtask') else '')
    return {'id':task['id'],'question':task['messages'][1]['content'],
       'task_specification':specs[spec_key],'model_final_answer':prediction,
       'reference_answer':gold.get('reference_answer'),
       'accepted_names':gold.get('accepted_names'),
       'preferred_name':gold.get('preferred_name'),
       'structured_gold':gold.get('structured_grounding'),
       'private_facts':gold.get('private_facts_for_judging')}


def judge_input_v1(task,gold,specs,prediction):
    from evaluator.final_answer import final_region
    payload=judge_input(task,gold,specs,final_region(prediction))
    payload['public_structure_evidence']=frozen_evidence(task)
    return payload


def parse_grade(text):
    obj=json.loads(text)
    if not isinstance(obj,dict) or set(obj)!={'score','reason'}:
        raise ValueError('Judge returned the wrong schema')
    if type(obj['score']) is not int or obj['score'] not in (0,1,2):
        raise ValueError('Judge score must be an integer 0/1/2')
    if not isinstance(obj['reason'],str) or not obj['reason'].strip() or len(obj['reason'])>2000:
        raise ValueError('Judge reason must be a short nonempty string')
    return obj


class JudgeFailure(RuntimeError):
    def __init__(self, sample_id, attempts):
        super().__init__('Judge attempts exhausted for '+sample_id)
        self.audit={'id':sample_id,'attempts':attempts,'status':'failed'}


class OpenAICompatibleJudge:
    """Replace this class or configure any compatible endpoint; one fresh request per item."""
    def __init__(self, config_path=None):
        self.config_path=Path(config_path or ROOT/'configs/judge.yaml')
        self.config=yaml.safe_load(self.config_path.read_text())
        self.cfg=self.config['judge']
        if self.cfg['provider']!='openai-compatible': raise ValueError('Unsupported judge provider')
        template=Path(self.cfg['prompt_template'])
        if not template.is_absolute(): template=ROOT/template
        self.prompt=template.read_text(encoding='utf-8')
        self.key=os.environ.get(self.cfg['api_key_env'])
        if not self.key: raise ValueError('Judge API key environment variable is missing')
    def score(self, payload):
        cfg=self.cfg
        wire=request_bytes(payload,cfg,self.prompt)
        start=time.monotonic(); last_failure='unknown';attempt_logs=[]
        for attempt in range(1,cfg['max_attempts']+1):
            attempt_log={'attempt':attempt};attempt_logs.append(attempt_log)
            request=urllib.request.Request(cfg['base_url'].rstrip('/')+'/chat/completions',wire,
                    {'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            try:
                parts=[]; usage={}; finish=None; length=0
                with provider_slot('judge',cfg.get('global_concurrency',4)), urllib.request.urlopen(request,timeout=cfg['timeout_seconds']) as response:
                    for line in response:
                        if time.monotonic()-start>cfg['timeout_seconds']*cfg['max_attempts']:
                            raise TimeoutError('Judge wall clock budget exhausted')
                        if not line.startswith(b'data: ') or line.strip()==b'data: [DONE]':continue
                        event=json.loads(line[6:])
                        if event.get('usage'): usage=event['usage'];attempt_log['usage']=usage
                        for choice in event.get('choices',[]):
                            content=choice.get('delta',{}).get('content')
                            # reasoning_content is deliberately never accumulated or written.
                            if content:
                                length+=len(content)
                                if length>32768:raise ValueError('Judge output exceeded limit')
                                parts.append(content)
                            if choice.get('finish_reason'):finish=choice['finish_reason']
                if finish!='stop':raise ValueError('Judge did not finish normally')
                text=''.join(parts); grade=parse_grade(text)
                row={'id':payload['id'],**grade,'judge_model':cfg['model'],'timestamp':utc_now()}
                audit={'id':payload['id'],'request_sha256':digest(wire),
                    'response_sha256':digest(text.encode()),'prompt_template_sha256':digest(self.prompt.encode()),
                    'attempts':attempt,'latency_seconds':round(time.monotonic()-start,3),'usage':usage,
                    'temperature':cfg['temperature'],'reasoning_effort':cfg.get('reasoning_effort'),'enable_thinking':cfg.get('enable_thinking'),
                    'attempt_log':attempt_logs,'response_text':text}
                return row,audit
            except urllib.error.HTTPError as exc:
                last_failure='http_'+str(exc.code)
                attempt_log['error']=last_failure
                if exc.code not in (408,429,500,502,503,504):break
            except (OSError,ValueError,KeyError,TypeError) as exc:
                last_failure=type(exc).__name__
                attempt_log['error']=last_failure
            if attempt<cfg['max_attempts']:time.sleep(min(2**attempt,8))
        raise JudgeFailure(payload['id'],attempt_logs)
