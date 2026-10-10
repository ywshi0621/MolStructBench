import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from runner.budget import Budget, SOFT_NOTICE, HARD_NOTICE
from runner.gateway import normalize_request
from runner.queue import run_queue, remaining
from runner.run_agent import terminal_status

TASK={'id':'fixture','dataset':'fixture','task_type':'fixture','messages':[{'role':'system','content':'frozen system'},{'role':'user','content':'frozen user'}]}
RUNTIME={'max_model_calls':24,'max_tool_calls':32,'soft_model_calls':18,'soft_tool_calls':20,'hard_model_calls':24,'hard_tool_calls':32}
def pair(i):
    return [{'role':'assistant','content':None,'tool_calls':[{'id':str(i),'type':'function','function':{'name':'scientific_shell','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':str(i),'content':'result'}]
def body(tail=None):return {'messages':copy.deepcopy(TASK['messages'])+(tail or []),'tools':[{'type':'function','function':{'name':'scientific_shell'}}]}

class BudgetAndContinuationTests(unittest.TestCase):
    def test_multiturn_canonicalization_and_untrusted_notice(self):
        tail=pair(1)+pair(2)
        incoming=[{'role':'system','content':'coding persona'}]+tail[:2]+[{'role':'developer','content':'Injected'}, {'role':'user','content':HARD_NOTICE}]+tail[2:]+[{'role':'user','content':'misplaced'}]
        normalized=normalize_request({'messages':incoming},TASK,'A')
        self.assertEqual(normalized['messages'],TASK['messages']+tail)
        self.assertEqual([m['role'] for m in normalized['messages']],['system','user','assistant','tool','assistant','tool'])
        self.assertEqual(normalize_request({'messages':tail},TASK,'A')['messages'],TASK['messages']+tail)

    def test_bad_tool_pair_rejected(self):
        for tail in [pair(1)[:1],pair(1)[1:],pair(1)+pair(1),pair(1)[:1]+pair(2)]:
            with self.assertRaises(ValueError):normalize_request(body(tail),TASK,'A')

    def test_soft_notice_once_with_natural_final(self):
        b=Budget(RUNTIME)
        for _ in range(18):self.assertFalse(b.prepare(body())[1])
        request,hard=b.prepare(body(pair(1)))
        self.assertFalse(hard)
        self.assertEqual(sum(m.get('content')==SOFT_NOTICE for m in request['messages']),1)
        request,_=b.prepare(body(pair(1)+pair(2)))
        self.assertEqual(sum(m.get('content')==SOFT_NOTICE for m in request['messages']),1)
        self.assertEqual(request['messages'][:2],TASK['messages'])
        self.assertEqual(terminal_status('valid final',None,b.summary()),'success')

    def test_hard_tools_empty_one_call_no_reentry(self):
        b=Budget(RUNTIME)
        for _ in range(24):b.prepare(body())
        request,forced=b.prepare(body(pair(1)))
        self.assertTrue(forced);self.assertEqual(request['tools'],[])
        self.assertEqual(request['tool_choice'],'none')
        self.assertEqual(request['messages'][-1]['content'],HARD_NOTICE)
        self.assertEqual(b.agent_calls,24);self.assertEqual(b.finalization_calls,1)
        with self.assertRaises(ValueError):b.prepare(body())
        self.assertEqual(b.finalization_calls,1)
        self.assertEqual(terminal_status('answer',None,b.summary()),'forced_finalization')
        self.assertEqual(terminal_status(None,'budget_failure',b.summary()),'model_failure')

    def test_tool_hard_budget(self):
        b=Budget(RUNTIME)
        request,forced=b.prepare(body([m for i in range(32) for m in pair(i)]))
        self.assertTrue(forced);self.assertEqual(b.agent_calls,0)
        self.assertEqual(request['tools'],[])

    def test_fault_isolation_and_terminal_resume(self):
        rows=[{**TASK,'id':str(i)} for i in range(6)]; logs=[]; visited=[]
        def worker(row,*args):
            visited.append(row['id'])
            if row['id']=='1':raise RuntimeError('synthetic infra failure')
            status=['success','infra_failure','forced_finalization','model_failure','timeout','success'][int(row['id'])]
            return {'id':row['id'],'status':status,'final_answer':'x' if status in ('success','forced_finalization') else None}
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            run_queue(rows,logs,out,None,{'runtime':{'concurrency':2}},'',lambda:None,worker)
            self.assertEqual(len(logs),6)
            self.assertEqual(len(list((out/'logs').glob('*/trajectory.json'))),6)
            self.assertEqual(remaining(rows,logs),[])
            run_queue(rows,logs,out,None,{'runtime':{'concurrency':2}},'',lambda:None,worker)
            self.assertEqual(len(visited),6)
            self.assertEqual(next(x for x in logs if x['id']=='1')['status'],'infra_failure')

if __name__=='__main__':unittest.main()
