"""Transport-only differences; all prompts, tools and budgets remain shared."""
import copy,json,time
class UnsupportedProvider(ValueError):pass
class ProviderAdapter:
    def __init__(self,model):
        self.model=model;self.transport=model.get('transport','chat_completions');self.reasoning={}
        if self.transport not in ('chat_completions','responses'):raise UnsupportedProvider(self.transport)
    def prepare(self,body):
        if self.transport=='chat_completions':
            request=copy.deepcopy(body);field=self.model.get('token_limit_field','max_tokens')
            if field not in ('max_tokens','max_completion_tokens'):raise UnsupportedProvider('Unknown token limit field')
            if field!='max_tokens':request[field]=request.pop('max_tokens')
            return request,'/chat/completions'
        items=[]
        for m in body['messages']:
            if m['role']=='tool':items.append({'type':'function_call_output','call_id':m['tool_call_id'],'output':m['content']})
            else:
                if m.get('content'):items.append({'role':m['role'],'content':m['content']})
                for tc in m.get('tool_calls') or []:
                    items.extend(copy.deepcopy(self.reasoning.get(tc['id'],[])))
                    items.append({'type':'function_call','call_id':tc['id'],**tc['function']})
        request={'model':body['model'],'input':items,'stream':True,'store':False,'max_output_tokens':body['max_tokens']}
        if self.model.get('temperature') is not None:request['temperature']=self.model['temperature']
        if body.get('reasoning_effort') is not None:
            request['reasoning']={'effort':body['reasoning_effort']}
            if self.model.get('responses_include_encrypted_reasoning',True):request['include']=['reasoning.encrypted_content']
        if body.get('tools'):
            request['tools']=[{'type':'function',**t['function'],'strict':False} for t in body['tools']]
        choice=body.get('tool_choice')
        if choice is not None:request['tool_choice']=({'type':'function','name':choice['function']['name']} if isinstance(choice,dict) else choice)
        return request,'/responses'
    def terminal(self,event):
        return event.get('type')=='response.completed' if self.transport=='responses' else any(c.get('finish_reason') for c in event.get('choices',[]))
    def convert(self,lines):
        if self.transport!='responses':return lines,None,None
        completed=None
        for line in lines:
            if line.startswith(b'data:') and line[5:].strip()!=b'[DONE]':
                event=json.loads(line[5:].strip())
                if event.get('type')=='response.completed':completed=event['response']
        if not completed or completed.get('status','completed')!='completed':raise OSError('Incomplete Responses output')
        output=completed.get('output',[]);calls=[r for r in output if r['type']=='function_call']
        memory=[r for r in output if r['type']=='reasoning']
        if calls:self.reasoning[calls[0]['call_id']]=memory
        raw=completed.get('usage') or {};usage={'prompt_tokens':raw.get('input_tokens',0),'completion_tokens':raw.get('output_tokens',0),
            'total_tokens':raw.get('total_tokens',raw.get('input_tokens',0)+raw.get('output_tokens',0)),
            'prompt_tokens_details':raw.get('input_tokens_details',{}),'completion_tokens_details':raw.get('output_tokens_details',{}),
            'responses_usage_raw':raw} if raw else None
        converted=[]
        def emit(delta,finish=None,u=None):
            chunk={'id':completed.get('id','resp'),'object':'chat.completion.chunk','created':int(time.time()),'model':completed.get('model',self.model['name']),
                   'choices':[{'index':0,'delta':delta,'finish_reason':finish}]}
            if u:chunk['usage']=u
            converted.append(('data: '+json.dumps(chunk)+'\n\n').encode())
        emit({'role':'assistant','content':''})
        # Preserve accompanying model text as well as native tool calls.
        text=''.join(part.get('text',part.get('refusal','')) for row in output if row['type']=='message' for part in row.get('content',[]))
        if text:emit({'content':text})
        if calls:
            emit({'tool_calls':[{'index':i,'id':r['call_id'],'type':'function','function':{'name':r['name'],'arguments':r['arguments']}} for i,r in enumerate(calls)]})
        emit({},'tool_calls' if calls else 'stop',usage);converted.append(b'data: [DONE]\n\n')
        return converted,usage,completed.get('model')
