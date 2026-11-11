import pandas as pd
import json
from rdkit.Chem import Draw,AllChem
import sys
from collections import namedtuple
from rdkit import Chem
from rich import print as rprint

class NCN():
    def __init__(self, smi = None, mol = None) -> None:
        self.mol = None
        if smi:
            self.mol = Chem.MolFromSmiles(smi)
        else:
            self.mol = mol

    def ExtratChain(self, mol):
        bonds = mol.GetBonds()
        rings = mol.GetRingInfo()
        bond_cut = []
        for bond in bonds:
            if not bond.IsInRing():
                BondGroupAtoms = (bond.GetBeginAtomIdx(),bond.GetEndAtomIdx())
                for RingGroupAtoms in rings.AtomRings():
                    if set(BondGroupAtoms) & set(RingGroupAtoms):
                        # 还需要保证切下来的不是一个原子，保证个锤子........
                        # 保证BondGroupAtoms是小在前
                        # 扯蛋，直接获取bond索引，OK？
                        bond_cut.append(mol.GetBondBetweenAtoms(*BondGroupAtoms).GetIdx())
        if not bond_cut:
            return ([],[])
        else:
            # 切割
            new = Chem.FragmentOnBonds(mol, list(set(bond_cut)))
            # 分割成片段
            frags = Chem.GetMolFrags(new, asMols=True)
            chains = []
            rings = []
            for frag in frags:
                frag_ring_info = frag.GetRingInfo()
                if not frag_ring_info.NumRings():
                    chains.append(frag)
                else:
                    rings.append(frag)

            return (chains, rings)

    def replaceStarMarker(self,mol):
        if type(mol) != Chem.rdchem.RWMol:
            mol = Chem.RWMol(mol)
        atomSymbol_list = [i.GetSymbol() for i in mol.GetAtoms()]
        atomIndex_list = [i.GetIdx() for i in mol.GetAtoms()]
        if "*" not in atomSymbol_list:
            _ = Chem.MolToSmiles(mol.GetMol(),isomericSmiles=True,canonical=True,kekuleSmiles=True)
            return Chem.MolFromSmiles(_)
        else:

            var = atomIndex_list[atomSymbol_list.index("*")]
            mol.ReplaceAtom(var, Chem.Atom(1))
            #mol.RemoveAtom(var)   
            return self.replaceStarMarker(mol) 

    def CheckAromaticity(self, ring):
        # if any bond in ring is aromaticity, the ring is aromaticity. 
        rinfo= ring.GetRingInfo()
        bonds = rinfo.BondRings()[0]
        bondsobj = ring.GetBonds()
        bonds, bondsobj
        flag=True
        for bondid in bonds:
            if not bondsobj[bondid].GetIsAromatic():
                flag=False
                break
        return flag


    def CheckPoly(self, chains, rings):
        out = {"N2":0,"N3":0,"Nn":0}
        # chains
        for chain in chains:
            count = 0
            for atom in chain.GetAtoms():
                if atom.GetSymbol() == "N":
                    count += 1
                    #print("Atom[{}]:{}".format(atom.GetIdx(), atom.GetSymbol()))
            if count == 0 or count == 1:
                pass
            elif count == 2:
                out["N2"] = 1
            elif count == 3:
                out["N3"] = 1
            else:
                out["Nn"] = 1  
        # rings
        for ring in rings:
            _ring = self.replaceStarMarker(ring)
            if self.CheckAromaticity(_ring):
                pass
            else:
                count = 0
                for atom in ring.GetAtoms():
                    if atom.GetSymbol() == "N":
                        count += 1
                if count == 0 or count == 1:
                    pass
                elif count == 2:
                    out["N2"] = 1
                elif count == 3:
                    out["N3"] = 1
                else:
                    out["Nn"] = 1  
        return out
    def __CheckOut__(self, out):
        if out["N2"] + out["N3"] + out["Nn"] > 0:
            return True
        else:
            return False

    def run(self,print_info= False):
        chains,rings = self.ExtratChain(self.mol)
        _out = self.CheckPoly(chains, rings) 
        flag = self.__CheckOut__(_out)
        if print_info:
            print("The Molecule is Polyamine-Conjugate: {}\n\tDiamine:{}\n\tTriamine:{}\n\tPolyamine:{}".format(flag
                                                                                                 , _out["N2"]
                                                                                                 , _out["N3"]))
        return flag, _out

