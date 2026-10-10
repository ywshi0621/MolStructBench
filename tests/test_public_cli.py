import copy,json,pathlib,tempfile,types,unittest
from scibench.cli import ROOT,model_config
from runner.adapter import load_public,prompt_hash
from runner.provider_adapters import ProviderAdapter
from runner.gateway import normalize_request
from runner.budget import Budget
from runner.queue import run_queue
class PublicContractTests(unittest.TestCase):
    def test_preflight_requires_successful_real_tool_result(self):
        from scripts.check_provider import verify_record
        record={'status':'success','agent_model_calls':2,'final_answer':'HASH 3.4.2','transport_checks':[{'original_messages_exact':True}],'tool_calls':[{'tool':'scientific_shell','output':json.dumps({'status':'error','exit_code':1,'output':'HASH 3.4.2'})}]}
        self.assertFalse(verify_record(record,'HASH'))
        record['tool_calls'][0]['output']=json.dumps({'status':'ok','exit_code':0,'output':'HASH 3.4.2'})
        self.assertTrue(verify_record(record,'HASH'))
    def test_nullable_temperature_not_passed_to_opencode_config(self):
        from runner.run_agent import make_config
        cfg=make_config(types.SimpleNamespace(url='http://localhost/v1'),'none',{'name':'new-model','temperature':None,'max_tokens':32768},{})
        self.assertNotIn('temperature',cfg['agent']['benchmark'])
        self.assertFalse(cfg['provider']['benchmark']['models']['new-model']['temperature'])
    def test_fixed_core_and_no_private_fields(self):
        rows,meta=load_public(ROOT/'data/benchmark_288_public.jsonl');self.assertEqual(len(rows),288)
        self.assertEqual(meta['task_units'],48);self.assertTrue(all('private_facts' not in r for r in rows))
        specs=json.loads((ROOT/'data/task_specifications.json').read_text());self.assertEqual(len(specs),48)
    def test_no_native_tools_is_explicitly_unsupported(self):
        cfg=json.loads((ROOT/'configs/chat.json').read_text());cfg['model']['tool_call']=False
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'model.json';p.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED'):model_config(types.SimpleNamespace(config=str(p),model='new-model',concurrency=1))
    def test_uniform_budget_cannot_be_changed_per_provider(self):
        cfg=json.loads((ROOT/'configs/chat.json').read_text());cfg['runtime']['max_tool_calls']=99
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'model.json';p.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'runtime mismatch'):model_config(types.SimpleNamespace(config=str(p),model='new-model',concurrency=1))
    def test_responses_function_call_roundtrip(self):
        model={'name':'arbitrary-model','transport':'responses','temperature':None};adapter=ProviderAdapter(model)
        body={'model':'arbitrary-model','max_tokens':32768,'messages':[{'role':'system','content':'public contract'},{'role':'user','content':'public question'},
             {'role':'assistant','content':None,'tool_calls':[{'id':'abc','function':{'name':'scientific_shell','arguments':'{"command":"echo hi"}'}}]},
             {'role':'tool','tool_call_id':'abc','content':'hi'}],'tools':[{'type':'function','function':{'name':'scientific_shell','parameters':{'type':'object'}}}]}
        wire,endpoint=adapter.prepare(body);self.assertEqual(endpoint,'/responses');self.assertNotIn('temperature',wire)
        self.assertEqual([i['type'] for i in wire['input'] if 'type' in i],['function_call','function_call_output'])
        self.assertEqual(wire['input'][-1]['call_id'],'abc');self.assertEqual(wire['input'][0]['content'],'public contract')
        completed={'type':'response.completed','response':{'id':'r','model':'arbitrary-model','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'FINAL'}]}],
            'usage':{'input_tokens':20,'output_tokens':10,'output_tokens_details':{'reasoning_tokens':7},'total_tokens':30}}}
        for prefix in ('data: ', 'data:'):
            lines,u,_=adapter.convert([(prefix+json.dumps(completed)+'\n').encode()]);self.assertIn(b'FINAL',b''.join(lines));self.assertEqual(u['completion_tokens'],10)
    def test_unauthorized_tool_definition_rejected(self):
        rows,_=load_public(ROOT/'data/benchmark_288_public.jsonl');body={'messages':rows[0]['messages'],'tools':[{'function':{'name':'websearch'}}]}
        with self.assertRaisesRegex(ValueError,'Unauthorized'):normalize_request(body,rows[0],'A')
    def test_hard_budget_finalization_once(self):
        runtime=json.loads((ROOT/'configs/runtime_policy.json').read_text());budget=Budget(runtime)
        body={'messages':[{'role':'system','content':'x'},{'role':'user','content':'y'}],'tools':[{'type':'function'}]}
        for _ in range(24):budget.prepare(body)
        last,forced=budget.prepare(body);self.assertTrue(forced);self.assertEqual(last['tools'],[])
        with self.assertRaises(ValueError):budget.prepare(body)
    def test_288_terminal_checkpoints_resume_without_calls(self):
        rows,_=load_public(ROOT/'data/benchmark_288_public.jsonl');logs=[];calls=[]
        def fixture(row,*args):
            calls.append(row['id']);return {'id':row['id'],'status':'success','final_answer':'PROTOCOL_FIXTURE_NOT_A_MODEL_SCORE'}
        with tempfile.TemporaryDirectory() as d:
            out=pathlib.Path(d);(out/'logs').mkdir();cfg={'runtime':{'concurrency':3}}
            run_queue(rows,logs,out,None,cfg,'test',lambda:None,worker=fixture);self.assertEqual(len(logs),288)
            run_queue(rows,logs,out,None,cfg,'test',lambda:None,worker=fixture);self.assertEqual(len(calls),288)
if __name__=='__main__':unittest.main()
