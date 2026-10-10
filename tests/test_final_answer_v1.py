"""Contract-level parser regressions; no sample or solver identities."""
import unittest

from evaluator.deterministic_r2 import deterministic_score


def grade(metric, answer, **gold):
    return deterministic_score(answer, {"metric_type": metric, **gold})[0]


class FinalAnswerV1Tests(unittest.TestCase):
    def test_repeated_final_headings_preserve_conflicts(self):
        gold = {"reference_answer": "Conformer A"}
        self.assertEqual(grade("conformer_choice", "Final answer: B\nFinal answer: A", **gold), 0)
        self.assertEqual(grade("conformer_choice", "Analysis: B\nFinal answer: A", **gold), 1)

    def test_two_standalone_final_answers_are_conflicting(self):
        gold = {"reference_answer": "Conformer A"}
        self.assertEqual(grade("conformer_choice", "A\nB", **gold), 0)
        self.assertEqual(grade("conformer_choice", "Conformer B was considered.\nA", **gold), 1)
        atoms = {"structured_grounding": {"atom_indices": [3, 4]}}
        self.assertEqual(grade("atom_set_exact", "[8, 9]\n[3, 4]", **atoms), 0)
        self.assertEqual(grade("atom_set_exact", "Candidate [8, 9].\n[3, 4]", **atoms), 1)

    def test_json_markdown_and_bilingual_name(self):
        atoms = {"structured_grounding": {"atom_indices": [3, 4]}}
        self.assertEqual(grade("atom_set_exact", "## Final answer\n```json\n{\"atom_indices\":[4,3]}\n```", **atoms), 1)
        name = {"accepted_names": ["Pivampicillin", "匹氨西林"], "reference_answer": "Pivampicillin"}
        self.assertEqual(grade("accepted_name_exact", "匹氨西林（Pivampicillin）", **name), 1)

    def test_coordinate_columns_and_named_axes(self):
        box=[1,2,3,4,5,6]
        table='| center | CIP | xmin | ymin | zmin | xmax | ymax | zmax |\n|---|---|---|---|---|---|---|---|\n| 9 | S | 1 | 2 | 3 | 4 | 5 | 6 |'
        self.assertEqual(grade('ordered_box3d_plus_cip',table,target_boxes=[box],target_cip_labels=['S']),1)
        self.assertEqual(grade('ordered_box3d_tol_0.01A','{"xmin":1,"ymin":2,"zmin":3,"xmax":4,"ymax":5,"zmax":6}',target_boxes=[box]),1)
        self.assertEqual(grade('ordered_box3d_tol_0.01A',table+'\n| 10 | R | 1 | 2 | 3 | 4 | 5 | 9 |',target_boxes=[box]),0)

    def test_property_json_table_wrapper_and_conflicts(self):
        g={'reference_answer':'TPSA: elevated; cLogP: intermediate.'}
        self.assertEqual(grade('normalized_exact','结果：TPSA: 偏高; cLogP: 中等',**g),1)
        self.assertEqual(grade('normalized_exact','{"cLogP":"intermediate","TPSA":"elevated"}',**g),1)
        self.assertEqual(grade('normalized_exact','| TPSA | cLogP |\n|---|---|\n| elevated | intermediate |',**g),1)
        self.assertEqual(grade('normalized_exact','TPSA: elevated; cLogP: intermediate\nTPSA: high',**g),0)

    def test_scaffold_json_field_order_and_prose_contradiction(self):
        g={'structured_grounding':{'scaffold_atom_indices':[2,3],'substituent_groups':[[0,1],[4]]}}
        answer='{"substituent_groups":[[0,1],[4]],"scaffold_atom_indices":[3,2]}'
        self.assertEqual(grade('scaffold_plus_groups_exact',answer,**g),1)
        self.assertEqual(grade('scaffold_plus_groups_exact',answer+'\nScaffold atoms: [2,5]',**g),0)

    def test_parent_smiles_equivalence_and_contradictory_assertions(self):
        g={'target_parent_smiles':'CCO'}
        self.assertEqual(grade('canonical_smiles_exact','Parent SMILES: OCC',**g),1)
        self.assertEqual(grade('canonical_smiles_exact','```json\n{"parent_smiles":"OCC"}\n```',**g),1)
        self.assertEqual(grade('canonical_smiles_exact','SMILES: CCO\nSMILES: CCC',**g),0)


if __name__ == "__main__":
    unittest.main()
