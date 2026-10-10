"""Evaluation-side audit helpers; these never supply an agent with gold.

The non-ring predicate is from the recovered molalign featurizer. The legacy
3D-to-2D diagnostic path reconstruction preserves set traversal/tie order;
unlike the Pure2D threshold witness, it also records paths shorter than five.
"""
import re
from rdkit import Chem

def eligible_carbons(mol):
    return {a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum()==6
            and a.GetHybridization()==Chem.HybridizationType.SP3 and not a.IsInRing()}

def longest_acyclic_path(mol):
    eligible=eligible_carbons(mol);best=[]
    for start in eligible:
        stack=[(start,[start])]
        while stack:
            current,path=stack.pop()
            if len(path)>len(best):best=path
            neighbors={a.GetIdx() for a in mol.GetAtomWithIdx(current).GetNeighbors()}
            for neighbor in sorted(neighbors & eligible-set(path),reverse=True):
                stack.append((neighbor,path+[neighbor]))
    return best

def threshold_witness(mol,minimum=5):
    eligible=eligible_carbons(mol)
    for start in sorted(eligible):
        stack=[(start,[start])]
        while stack:
            current,path=stack.pop()
            if len(path)>=minimum:return path
            neighbors={a.GetIdx() for a in mol.GetAtomWithIdx(current).GetNeighbors()}
            for neighbor in sorted(neighbors & eligible-set(path),reverse=True):stack.append((neighbor,path+[neighbor]))
    return []

def public_molecule(text):
    smiles=re.search(r'^SMILES: (.+)$',text,re.M)
    if smiles:return Chem.MolFromSmiles(smiles.group(1))
    rw=Chem.RWMol()
    for line in text.split('Atoms (index, element, formal_charge, x, y, z):\n')[1].split('Bonds (atom_i, atom_j, bond_order):')[0].strip().splitlines():
        parts=line.split();atom=Chem.Atom(parts[1]);atom.SetFormalCharge(int(parts[2]))
        if rw.AddAtom(atom)!=int(parts[0]):raise ValueError('Atom order mismatch')
    for line in text.split('Bonds (atom_i, atom_j, bond_order):\n')[1].split('\n\n')[0].strip().splitlines():
        a,b,order=line.split();rw.AddBond(int(a),int(b),{1:Chem.BondType.SINGLE,2:Chem.BondType.DOUBLE,3:Chem.BondType.TRIPLE,1.5:Chem.BondType.AROMATIC}[float(order)])
    mol=rw.GetMol();Chem.SanitizeMol(mol);return mol
