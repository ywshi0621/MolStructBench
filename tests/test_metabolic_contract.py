import unittest
from rdkit import Chem
from evaluator.metabolic_contract import threshold_witness,longest_acyclic_path

class MetabolicContractTests(unittest.TestCase):
    def test_nonring_threshold(self):
        for smiles,expected in [('CCCCC',True),('CCCC',False),('C1CCCCC1',False),('CCCC1CCCCC1',False),('CC(C)(C)C',False),('CCOCC',False),('CCCCCC1CCCCC1',True)]:
            self.assertEqual(bool(threshold_witness(Chem.MolFromSmiles(smiles))),expected,smiles)
    def test_distinct_diagnostic_field_semantics(self):
        mol=Chem.MolFromSmiles('CCC')
        self.assertEqual(threshold_witness(mol),[])
        self.assertEqual(longest_acyclic_path(mol),[0,1,2])
