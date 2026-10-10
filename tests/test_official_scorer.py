import unittest
from evaluator.official_scorer import aggregate,median_three,DATASETS,score_rows

class OfficialScorerTests(unittest.TestCase):
    def test_equal_dataset_weights_with_unequal_unit_counts(self):
        rows=[]
        for d,count in zip(DATASETS,(8,16,24)):
            for unit in range(count):
                for sample in range(6):
                    rows.append({'id':f'{d}:{unit}:{sample}','dataset':d,'task_type':str(unit),
                                 'score':float(d==DATASETS[0]),'metric_type':'normalized_exact'})
        self.assertAlmostEqual(aggregate(rows)['overall_score'],1/3)
        self.assertAlmostEqual(aggregate(rows)['micro_score'],1/6)
        rows[0]['score']=None
        self.assertIsNone(aggregate(rows)['overall_score'])

    def test_median_and_incomplete_calls(self):
        self.assertEqual(median_three([{'replicate':i+1,'score':s} for i,s in enumerate((0,2,2))]),1)
        self.assertEqual(median_three([{'replicate':i+1,'score':s} for i,s in enumerate((0,1,2))]),.5)
        with self.assertRaises(ValueError):median_three([{'replicate':1,'score':2}]*3)

    def test_public_accepted_set_accepts_each_variant_but_not_conflicts(self):
        public={'fixture':{'dataset':'data','task_type':'attachment'}}
        first={'metric_type':'bond_endpoint_exact','structured_grounding':{'atom_indices':[1,2]}}
        second={'metric_type':'bond_endpoint_exact','structured_grounding':{'atom_indices':[3,4]}}
        accepted={'fixture':{'accepted_variants':[first,second]}}
        def score(answer):return score_rows(public,{'fixture':first},{'fixture':answer},['fixture'],{},accepted)[0]['score']
        self.assertEqual(score('[3,4]'),1)
        self.assertEqual(score('[1,2] and [3,4]'),0)
        self.assertEqual(score('[5,6]'),0)

if __name__=='__main__':unittest.main()
