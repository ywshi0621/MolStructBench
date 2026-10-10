import copy,hashlib,json,pathlib,tempfile,unittest
from unittest.mock import patch
from scibench.cli import ROOT
from scibench.local_score import context,score_local,validate_vote
from evaluator.semantic_judge import judge_input_v1,OpenAICompatibleJudge
from evaluator.official_scorer import expected_judge_hash
from evaluator.judge_wire import request_bytes

class LocalScorerTests(unittest.TestCase):
    def setUp(self):
        index=json.loads((ROOT/'examples/history/INDEX.json').read_text());self.run=ROOT/'examples/history'/index['runs'][0]['key']
        self.public,self.gold,self.ids,self.preds,self.specs,self.accepted,self.config,self.prompt=context(self.run/'predictions.jsonl')

    def test_archived_wire_independent_of_live_rdkit_and_strict_tamper_checks(self):
        row=json.loads((self.run/'judge_triples.jsonl').read_text().splitlines()[0]);sid=row['id']
        with patch('evaluator.public_evidence.public_evidence',side_effect=RuntimeError('Different runtime must not rebuild historical evidence')):
            payload=judge_input_v1(self.public[sid],self.gold[sid],self.specs,self.preds[sid])
            self.assertEqual(expected_judge_hash(payload,self.config,self.prompt),row['audit']['request_sha256'])
            validate_vote(row,payload,self.config,self.prompt)
        for key,value in [('model_final_answer','changed answer'),('reference_answer','changed gold'),('question','changed question')]:
            modified={**payload,key:value}
            with self.assertRaises(ValueError):validate_vote(row,modified,self.config,self.prompt)
        changed=copy.deepcopy(row);changed['audit']['request_sha256']='0'*64
        with self.assertRaises(ValueError):validate_vote(changed,payload,self.config,self.prompt)
        changed=copy.deepcopy(row);changed['score']=(row['score']+1)%3
        with self.assertRaises(ValueError):validate_vote(changed,payload,self.config,self.prompt)

    def test_new_http_judge_uses_same_serializer_and_excludes_reasoning(self):
        row=json.loads((self.run/'judge_triples.jsonl').read_text().splitlines()[0]);sid=row['id'];payload=judge_input_v1(self.public[sid],self.gold[sid],self.specs,self.preds[sid]);sent=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def __iter__(self):
                yield b'data: {"choices":[{"delta":{"reasoning_content":"DO_NOT_SAVE"}}]}\n'
                yield ('data: '+json.dumps({'choices':[{'delta':{'content':'{"score":2,"reason":"TRANSPORT TEST FIXTURE"}'},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':5}})+'\n').encode()
        def urlopen(req,**kwargs):sent.append(req.data);return Response()
        with patch.dict('os.environ',{'DASHSCOPE_API_KEY':'TEST_ONLY_NOT_A_REAL_KEY'}),patch('urllib.request.urlopen',urlopen):
            judge=OpenAICompatibleJudge(ROOT/'configs/judge.yaml');grade,audit=judge.score(payload)
        self.assertEqual(sent,[request_bytes(payload,self.config,self.prompt)])
        self.assertEqual(audit['request_sha256'],row['audit']['request_sha256'])
        self.assertNotIn('DO_NOT_SAVE',json.dumps(audit));self.assertEqual(grade['score'],2)

    def test_missing_cache_pending_then_resume_reuses_valid_votes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);preds=root/'predictions.jsonl'
            changed=dict(self.preds);vote=json.loads((self.run/'judge_triples.jsonl').read_text().splitlines()[0]);changed[vote['id']]+=' NEW ANSWER FOR PENDING TEST'
            preds.write_text(''.join(json.dumps({'id':sid,'prediction':text},ensure_ascii=False)+'\n' for sid,text in changed.items()))
            result=score_local(preds,root/'results',offline=True)
            self.assertIsNone(result['official_v1_score']);self.assertGreater(result['pending_count'],0)
            with self.assertRaises(ValueError):score_local(self.run/'predictions.jsonl',root/'results',offline=True)

    def test_gold_never_in_solver_gateway_or_workspace(self):
        from runner.run_agent import workspace_view
        from runner.gateway import normalize_request
        task=next(iter(self.public.values()));view=workspace_view(task)
        self.assertEqual(set(view),{'id','messages'})
        body=normalize_request({'messages':[{'role':'system','content':'GOLD_CANARY'}]},task,'A')
        self.assertEqual(body['messages'],task['messages']);self.assertNotIn('GOLD_CANARY',json.dumps(body))
        from runner.sandbox import execute
        import sys
        with tempfile.TemporaryDirectory(dir='/dev/shm') as tmp:
            root=pathlib.Path(tmp)
            for name in ('input','output','tmp'):(root/name).mkdir()
            (root/'input/task.json').write_text(json.dumps(view))
            result=execute(root,sys.prefix,'cat '+str(ROOT/'data/benchmark_288_gold.jsonl'))
            self.assertEqual(result['status'],'error');self.assertNotIn('reference_answer',result['output'])

    def test_failed_vote_pending_and_only_missing_slot_retried(self):
        from evaluator.semantic_judge import JudgeFailure
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);preds=root/'predictions.jsonl'
            # Same answers with different file whitespace: explicit archive import,
            # then no automatic byte-hash cache on the next invocation.
            preds.write_text(''.join(json.dumps({'id':sid,'prediction':text},ensure_ascii=False,indent=None,separators=(',',':'))+'\n' for sid,text in self.preds.items()))
            out=root/'results';first=score_local(preds,out,[self.run],offline=True)
            self.assertEqual(first['pending_count'],0)
            checkpoint=next((out/'semantic_stage/checkpoints').glob('rep*/*.json'))
            record=json.loads(checkpoint.read_text());checkpoint.unlink()
            with patch.dict('os.environ',{'DASHSCOPE_API_KEY':'TEST_ONLY_NOT_A_REAL_KEY'}),patch.object(OpenAICompatibleJudge,'score',side_effect=JudgeFailure(record['id'],[{'attempt':1,'error':'fixture_503'}])) as failed:
                pending=score_local(preds,out);self.assertEqual(failed.call_count,1)
            self.assertEqual(pending['pending_count'],1);self.assertIsNone(pending['official_v1_score'])
            grade={k:v for k,v in record.items() if k not in ('replicate','audit')}
            with patch.dict('os.environ',{'DASHSCOPE_API_KEY':'TEST_ONLY_NOT_A_REAL_KEY'}),patch.object(OpenAICompatibleJudge,'score',return_value=(grade,record['audit'])) as resumed:
                final=score_local(preds,out);self.assertEqual(resumed.call_count,1)
            self.assertEqual(final['pending_count'],0);self.assertEqual(final['official_v1_score'],first['official_v1_score'])

if __name__=='__main__':unittest.main()
