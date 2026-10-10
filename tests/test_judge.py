import unittest
from evaluator.semantic_judge import parse_grade, judge_input
from scripts.run_judge_calibration import consistency

class JudgeTests(unittest.TestCase):
    def test_strict_grade_schema(self):
        self.assertEqual(parse_grade('{"score":2,"reason":"Equivalent expression."}')['score'],2)
        for x in ['{"score":true,"reason":"x"}','{"score":3,"reason":"x"}',
                  '{"score":1,"reason":""}','{"score":0,"reason":"x","thoughts":"hidden"}',
                  '```json\n{"score":2,"reason":"x"}\n```']:
            with self.assertRaises(ValueError):parse_grade(x)
    def test_judge_input_omits_source_mapping(self):
        task={'id':'scibench_000001','dataset':'d','task_type':'t','messages':[{}, {'content':'Question'}]}
        gold={'reference_answer':'Reference','structured_grounding':{},'private_facts_for_judging':{},
              'original_sample_id':'HIDDEN_SOURCE','source_split':'PRIVATE_SOURCE','original_reference_answer':'OBSOLETE'}
        payload=judge_input(task,gold,{'d::t':{}},'Candidate')
        self.assertEqual(payload['reference_answer'],'Reference')
        self.assertNotIn('original_sample_id',payload)
        self.assertNotIn('OBSOLETE',str(payload))
    def test_consistency_is_not_accuracy(self):
        a=[{'id':'a','score':0},{'id':'b','score':2}]
        b=[{'id':'a','score':1},{'id':'b','score':2}]
        r=consistency(a,b)
        self.assertEqual(r['exact_agreement_rate'],.5)
        self.assertEqual(r['mean_absolute_score_difference'],.5)
        self.assertEqual(r['disagreement_ids'],['a'])
if __name__=='__main__':unittest.main()
