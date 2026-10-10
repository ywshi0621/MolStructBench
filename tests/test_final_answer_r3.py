import unittest
from evaluator.deterministic_r2 import deterministic_score

def grade(metric,answer,**gold):
    return deterministic_score(answer,{'metric_type':metric,**gold})[0]

class FinalAnswerR3Tests(unittest.TestCase):
    def test_last_explicit_final_and_terminal_choice(self):
        g={'reference_answer':'Conformer A'}
        self.assertEqual(grade('conformer_choice','Analysis: conformer A has contact.\nFinal answer: B',**g),0)
        self.assertEqual(grade('conformer_choice','Conformer B was considered.\nA',**g),1)
        self.assertEqual(grade('conformer_choice','Final answer: A or B',**g),0)

    def test_box_cip_uses_final_assertions(self):
        box=[1,2,3,4,5,6];g={'target_boxes':[box],'target_cip_labels':['S']}
        self.assertEqual(grade('ordered_box3d_plus_cip','Analysis: candidate R/S.\n## Final answer\nAtom 3 — S\n[1,2,3,4,5,6]',**g),1)
        self.assertEqual(grade('ordered_box3d_plus_cip','## Final answer\nAtom 3 — R\n[1,2,3,4,5,6]',**g),0)
        self.assertEqual(grade('ordered_box3d_tol_0.01A','[1,2,3,4,5,6]\nThe box [1,2,3,4,5,6] is selected.',target_boxes=[box]),1)
        self.assertEqual(grade('ordered_box3d_tol_0.01A','[1,2,3,4,5,6]\n[1,2,3,4,5,7]',target_boxes=[box]),0)

    def test_atom_lists_json_table_and_terminal_answer(self):
        g={'structured_grounding':{'atom_indices':[1,2,3]}}
        self.assertEqual(grade('atom_set_exact','Candidate [8,9].\n## Answer\n{"atom_indices":[3,2,1]}',**g),1)
        self.assertEqual(grade('atom_set_exact','Candidate [8,9].\n[1,2,3]',**g),1)
        self.assertEqual(grade('atom_set_exact','Final answer: [1,2,3] and [8,9]',**g),0)
        bond={'structured_grounding':{'target_bond':{'atom_i':22,'atom_j':23,'bond_index':22}}}
        self.assertEqual(grade('bond_target_exact','| endpoints | [22,23] |\n| bond index | 22 |',**bond),1)
        self.assertEqual(grade('bond_target_exact','| endpoints | [22,23] |\n| bond index | 21 |',**bond),0)

    def test_scaffold_and_group_dedup(self):
        g={'structured_grounding':{'scaffold_atom_indices':[2,3],'substituent_groups':[[0,1],[4]]}}
        answer='Scaffold atoms:\n[2,3]\nSubstituent groups:\n[0,1]\n[4]\nSummary: [[0,1],[4]]'
        self.assertEqual(grade('scaffold_plus_groups_exact',answer,**g),1)
        self.assertEqual(grade('scaffold_plus_groups_exact',answer+'\n[5]',**g),0)

    def test_labels_names_and_deferred_identity(self):
        self.assertEqual(grade('normalized_exact','related_analog\nThis follows from Tanimoto.',reference_answer='related_analog'),1)
        self.assertEqual(grade('normalized_exact','related_analog, or close_analog',reference_answer='related_analog'),0)
        names={'accepted_names':['Pivampicillin','匹氨西林'],'reference_answer':'Pivampicillin'}
        self.assertEqual(grade('accepted_name_exact','匹氨西林（Pivampicillin）',**names),1)
        self.assertIsNone(grade('accepted_name_exact','未经身份核实的别名',accepted_names=['exampledrug'],reference_answer='exampledrug'))
        self.assertEqual(grade('accepted_name_exact','Pivampicillin or another drug',**names),0)

if __name__=='__main__':unittest.main()
