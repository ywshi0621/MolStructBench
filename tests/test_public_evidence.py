import unittest
from evaluator.public_evidence import public_evidence

class PublicEvidenceTests(unittest.TestCase):
    def test_donor_sites_are_not_donor_hydrogens(self):
        evidence=public_evidence('SMILES: NCCO')['molecules'][0]
        self.assertEqual(evidence['HBD_sites'],2)
        self.assertEqual(evidence['donor_hydrogens'],3)
        self.assertEqual(evidence['HBA_sites'],2)
        self.assertIn('[NH2:1]',evidence['source_mapped_smiles'])

    def test_pair_order_is_preserved(self):
        evidence=public_evidence('Molecule A:\nSMILES: CO\nMolecule B:\nSMILES: CCC')
        self.assertEqual([m['molecule'] for m in evidence['molecules']],['A','B'])
        self.assertEqual([m['HBD_sites'] for m in evidence['molecules']],[1,0])

if __name__=='__main__':unittest.main()
