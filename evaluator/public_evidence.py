"""Read-only scientific evidence reconstructed solely from public input."""
import re
from rdkit import Chem, rdBase
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

def molecules(question):
    smiles=re.findall(r'(?m)^SMILES:\s*(\S+)',question)
    if smiles:return [Chem.MolFromSmiles(s) for s in smiles]
    sections=re.split(r'Atoms \(index, element, formal_charge, x, y, z\):\n',question)[1:]
    result=[]
    for section in sections:
        atoms,bonds=section.split('Bonds (atom_i, atom_j, bond_order):\n',1)
        rw=Chem.RWMol()
        for line in atoms.splitlines():
            match=re.fullmatch(r'(\d+)\t([A-Z][a-z]?)\t(-?\d+)\t[-+\d.eE]+\t[-+\d.eE]+\t[-+\d.eE]+',line)
            if not match:continue
            idx,symbol,charge=match.groups()
            if int(idx)!=rw.GetNumAtoms():raise ValueError('Non-contiguous public indices')
            atom=Chem.Atom(symbol);atom.SetFormalCharge(int(charge));rw.AddAtom(atom)
        types={'1':Chem.BondType.SINGLE,'2':Chem.BondType.DOUBLE,'3':Chem.BondType.TRIPLE,'1.5':Chem.BondType.AROMATIC}
        for line in bonds.split('\n\n')[0].splitlines():
            match=re.fullmatch(r'(\d+)\t(\d+)\t([\d.]+)',line)
            if match:rw.AddBond(int(match[1]),int(match[2]),types[match[3]])
        mol=rw.GetMol();Chem.SanitizeMol(mol);result.append(mol)
    return result

def public_evidence(question):
    result=[]
    for index,mol in enumerate(molecules(question)):
        if mol is None:raise ValueError('Invalid public structure')
        for atom in mol.GetAtoms():atom.SetIntProp('_source_idx',atom.GetIdx())
        heavy=Chem.RemoveHs(mol)
        canonical=Chem.MolToSmiles(heavy,canonical=True,isomericSmiles=True)
        mapped=Chem.Mol(heavy)
        for atom in mapped.GetAtoms():atom.SetAtomMapNum(atom.GetIntProp('_source_idx')+1)
        donor_sites=heavy.GetSubstructMatches(Lipinski.HDonorSmarts)
        result.append({'molecule':'A' if index==0 else 'B','canonical_isomeric_smiles':canonical,
                       'source_mapped_smiles':Chem.MolToSmiles(mapped,isomericSmiles=True),
                       'map_number_rule':'atom map number = public zero-based atom index + 1',
                       'formula':rdMolDescriptors.CalcMolFormula(heavy),
                       'heavy_atoms':heavy.GetNumHeavyAtoms(),'HBD_sites':Lipinski.NumHDonors(heavy),
                       'HBA_sites':Lipinski.NumHAcceptors(heavy),
                       'donor_hydrogens':sum(heavy.GetAtomWithIdx(hit[0]).GetTotalNumHs() for hit in donor_sites),
                       'TPSA':Descriptors.TPSA(heavy),'cLogP':Crippen.MolLogP(heavy),'MW':Descriptors.MolWt(heavy)})
    return {'provenance':'Derived only from public SMILES or atom/bond tables; no solver identity, private gold or trajectory',
            'rdkit_version':rdBase.rdkitVersion,'molecules':result}
