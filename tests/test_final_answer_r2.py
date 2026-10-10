import unittest
from evaluator.deterministic_r2 import deterministic_score
from evaluator.final_answer import final_region

class FinalAnswerTests(unittest.TestCase):
    def score(self, text, metric, **gold):
        return deterministic_score(text, {'metric_type':metric, **gold})[0]

    def test_analysis_does_not_pollute_final_groups(self):
        self.assertEqual(self.score('## Analysis\n[1,2] and [3,4]\n## Final answer\n```json\n[[8]]\n```',
            'atom_group_set_exact',structured_grounding={'matches':[[8]]}),1)

    def test_json_bond_and_prose_duplicate(self):
        g={'target_bond':{'atom_i':7,'atom_j':8,'bond_index':3}}
        for p in ['{"atom_indices":[7,8],"bond_index":3}',
                  '## 结果\n```json\n{"atom_indices":[7,8],"bond_index":3}\n```\n端点原子：[8,7]；键索引：3']:
            self.assertEqual(self.score(p,'bond_target_exact',structured_grounding=g),1)

    def test_conflicting_final_json_and_prose_rejected(self):
        p='## Final answer\n{"atom_indices":[7,8],"bond_index":3}\nAtom indices: [2,3]'
        self.assertEqual(self.score(p,'bond_target_exact',structured_grounding={'target_bond':{'atom_i':7,'atom_j':8,'bond_index':3}}),0)

    def test_conflicting_final_sections_rejected(self):
        self.assertEqual(self.score('## Answer\n[1]\n## Answer\n[2]','atom_set_exact',structured_grounding={'atom_indices':[2]}),0)

    def test_cip_analysis_and_repetition(self):
        p='## Analysis\nR/S candidates\n## Output\nCIP=S\n[0,0,0,1,1,1]\nCIP=S [0,0,0,1,1,1]'
        self.assertEqual(self.score(p,'ordered_box3d_plus_cip',target_boxes=[[0,0,0,1,1,1]],target_cip_labels=['S']),1)
        self.assertEqual(self.score(p+'\nCIP=R','ordered_box3d_plus_cip',target_boxes=[[0,0,0,1,1,1]],target_cip_labels=['S']),0)

    def test_rounded_box_repetition_and_order(self):
        g={'target_boxes':[[0.123456,0,0,1,1,1],[2,2,2,3,3,3]]}
        self.assertEqual(self.score('[0.123456,0,0,1,1,1] [2,2,2,3,3,3]\nRounded: [0.123,0,0,1,1,1] [2,2,2,3,3,3]','ordered_box3d_tol_0.01A',**g),1)
        self.assertEqual(self.score('[2,2,2,3,3,3] [0.123456,0,0,1,1,1]','ordered_box3d_tol_0.01A',**g),0)
        self.assertEqual(self.score('[0.123456,0,0,1,1,1] [2,2,2,3,3,3] [4,4,4,5,5,5]','ordered_box3d_tol_0.01A',**g),0)

    def test_bilingual_name_not_substring_or_alternatives(self):
        g={'accepted_names':['exampledrug','示例药']}
        self.assertEqual(self.score('示例药（ExampleDrug）','accepted_name_exact',**g),1)
        for p in ['not exampledrug','exampledrug or otherdrug']:
            self.assertEqual(self.score(p,'accepted_name_exact',**g),0)
        for p in ['exampledrug (otherdrug)','prefixexampledrug']:
            self.assertIsNone(self.score(p,'accepted_name_exact',**g))

    def test_analysis_heading_not_a_final_heading(self):
        p='## Analysis results\nR/S\n## Final answer\nS'
        self.assertEqual(final_region(p),'S')

    def test_label_json(self):
        self.assertEqual(self.score('```json\n{"label":"yes"}\n```','normalized_exact',reference_answer='yes'),1)

if __name__=='__main__':unittest.main()
