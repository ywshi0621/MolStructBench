import copy,unittest
from evaluator.official_scorer import expected_judge_hash

class JudgeTransportPolicyTests(unittest.TestCase):
    def test_longer_wait_preserves_request_but_generation_changes_do_not(self):
        payload={'id':'fixture','question':'public contract','model_final_answer':'answer'}
        baseline={'model':'fixture-model','temperature':0.6,'max_tokens':8192,'enable_thinking':True,'reasoning_effort':'high','timeout_seconds':180,'max_attempts':3}
        expected=expected_judge_hash(payload,baseline,'fixed judge instructions')
        extended=copy.deepcopy(baseline);extended['timeout_seconds']=1800
        self.assertEqual(expected,expected_judge_hash(payload,extended,'fixed judge instructions'))
        for key,value in [('reasoning_effort','medium'),('temperature',0),('max_tokens',16384),('model','another-model'),('enable_thinking',False)]:
            changed={**extended,key:value}
            self.assertNotEqual(expected,expected_judge_hash(payload,changed,'fixed judge instructions'))
if __name__=='__main__':unittest.main()
