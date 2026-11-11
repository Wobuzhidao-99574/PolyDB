# =====================================================
# 文件名：services/chemistry_service.py
# 作用：RDKit 化学计算相关函数
# =====================================================

import io
import base64
from io import BytesIO

from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem, Descriptors, Draw, MACCSkeys, rdMolDescriptors
from rdkit.Chem.Draw import SimilarityMaps, rdMolDraw2D
from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator
from PIL import Image, ImageOps


# --------------------------------------------------
# SMILES → 分子对象 + 3D图片（重型函数，只在需要3D时调用）
# --------------------------------------------------
def ReadSmi(smi_ss: str):
    """
    从 SMILES 生成带H的3D优化分子（耗时较长，勿在搜索结果中批量调用）
      - mol: 带H的3D优化分子
      - noHmol: 去H的2D分子（用于展示）
      - img: PIL Image
      - ff: MMFF94 力场对象
    """
    smi_ss = smi_ss.rstrip("\n")
    mol = Chem.MolFromSmiles(smi_ss)
    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, randomSeed=10,
                          useExpTorsionAnglePrefs=True,
                          useBasicKnowledge=True)
    AllChem.MMFFOptimizeMolecule(mol)
    ff = AllChem.MMFFGetMoleculeForceField(mol, AllChem.MMFFGetMoleculeProperties(mol))
    noHmol = Chem.RemoveHs(mol)
    AllChem.Compute2DCoords(noHmol)
    AllChem.AssignStereochemistry(noHmol)
    img = Draw.MolToImage(noHmol)
    return mol, noHmol, img, ff


# --------------------------------------------------
# PIL Image → base64 data URI
# --------------------------------------------------
def pil_to_base64(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


# --------------------------------------------------
# SMILES → base64（只做2D，不做3D优化，速度快10x以上）
# 搜索结果列表展示用这个
# --------------------------------------------------
def smiles_to_base64(smiles: str) -> str:
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        AllChem.Compute2DCoords(mol)
        img = Draw.MolToImage(mol)
        return pil_to_base64(img)
    except Exception:
        return ""


# --------------------------------------------------
# Gasteiger 电荷相似度图
# --------------------------------------------------
def GasMaps(mol) -> Image.Image:
    AllChem.ComputeGasteigerCharges(mol)
    contribs = [
        round(mol.GetAtomWithIdx(i).GetDoubleProp('_GasteigerCharge'), 2)
        for i in range(mol.GetNumAtoms())
    ]
    draw2d = rdMolDraw2D.MolDraw2DCairo(2000, 2000)
    draw2d.SetLineWidth(3)
    SimilarityMaps.GetSimilarityMapFromWeights(
        mol, contribs, colorMap='PRGn', contourLines=10, draw2d=draw2d
    )
    draw2d.FinishDrawing()
    img = Image.open(io.BytesIO(draw2d.GetDrawingText()))
    return ImageOps.crop(img, border=200)


# --------------------------------------------------
# LogP 贡献相似度图
# --------------------------------------------------
def LogPMaps(mol) -> Image.Image:
    crippen = rdMolDescriptors._CalcCrippenContribs(mol)
    mol_log = [x for x, _ in crippen]
    draw2d = rdMolDraw2D.MolDraw2DCairo(2000, 2000)
    draw2d.SetLineWidth(3)
    SimilarityMaps.GetSimilarityMapFromWeights(
        mol, mol_log, colorMap='PRGn', contourLines=10, draw2d=draw2d
    )
    draw2d.FinishDrawing()
    img = Image.open(io.BytesIO(draw2d.GetDrawingText()))
    return ImageOps.crop(img, border=200)


# --------------------------------------------------
# Lipinski 规则判断
# --------------------------------------------------
def Lipinski(mw, hba, hbd, logp, rotb) -> dict:
    return {
        "MolWt":  ("✔️" if mw <= 500 else "❌"),
        "HBA":    ("✔️" if hba <= 10 else "❌"),
        "HBD":    ("✔️" if hbd <= 5 else "❌"),
        "LogP":   ("✔️" if -2 <= logp <= 5 else "❌"),
        "ROTB":   ("✔️" if rotb <= 10 else "❌"),
    }


# --------------------------------------------------
# Tanimoto 相似度计算（单对分子，路线搜索内部用）
# --------------------------------------------------
def cal_similarities(smiles_query: str, smiles_target: str) -> float:
    mol_q = Chem.MolFromSmiles(smiles_query)
    mol_t = Chem.MolFromSmiles(smiles_target)
    if mol_q is None or mol_t is None:
        return 0.0
    fpgen = GetMorganGenerator(radius=2)
    fp_q = fpgen.GetFingerprint(mol_q)
    fp_t = fpgen.GetFingerprint(mol_t)
    return DataStructs.FingerprintSimilarity(fp_q, fp_t)


# --------------------------------------------------
# MACCS 指纹相似度搜索（本地，不依赖 PostgreSQL 扩展）
# --------------------------------------------------
def DBSearch(smi: str, db: list, lim: int = 30) -> list:
    """
    db: [(id, smiles), ...]
    返回: [(id, similarity), ...] 按相似度降序
    """
    mol_in = Chem.MolFromSmiles(smi)
    if mol_in is None:
        return []
    fp_in = MACCSkeys.GenMACCSKeys(mol_in)
    results = []
    for mol_id, mol_smi in db:
        m = Chem.MolFromSmiles(mol_smi)
        if m is None:
            continue
        fp = MACCSkeys.GenMACCSKeys(m)
        sim = DataStructs.TanimotoSimilarity(fp, fp_in)
        results.append((mol_id, sim))
    return sorted(results, key=lambda x: x[1], reverse=True)[:lim]
