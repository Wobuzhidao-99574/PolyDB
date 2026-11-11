# -*- coding: utf-8 -*-
"""
核查 PolyDB 中 spermidine / spermine 分类是否存在"非真实胺氮被误计入多胺氮"的问题（完整版）。

相比上一版，本版将"自由胺氮"的判定规则从"仅排除酰胺氮"扩展为排除以下几类
在化学上不具备正常脂肪胺碱性/质子化能力的氮：
  1. 酰胺 / 脲 / 氨基甲酸酯氮   (N-C(=O)-X)
  2. 磺酰胺 / 亚磺酰胺氮       (N-S(=O)...)
  3. 直接连接芳香环的氮        (苯胺型；环内芳香氮本身也会被此规则一并排除)
  4. 氰基氮                   (N#C，叁键氮)
  5. 硝基 / 亚硝基氮           (N上带=O)

胍基(guanidine)、脂肪伯/仲/叔胺、天然多胺骨架本身的氮，不受影响，仍计为"自由胺氮"。

方法：
1. 从数据库读出所有 category in ('spermidine','spermine') 的记录
2. 复用 NCN.py 的思路（沿环-链连接键切开分子，得到链碎片/环碎片）
3. 对每个碎片，用扩展后的规则统计"自由胺氮"个数
4. 判断：排除掉这些非真实胺氮后，该记录是否仍满足 N>=2（是否仍够格留在原分类）
5. 输出：总体统计 + 不合格记录明细 CSV（额外标注具体是被哪类基团影响的）

用法（在服务器、能连数据库、已装 rdkit 的环境下）：
    pip install psycopg2-binary --break-system-packages   # 如未安装
    python3 check_amide_misclassification_v2.py
"""
import csv
import psycopg2
from rdkit import Chem

# ------------------ 数据库连接配置，按需修改 ------------------
DB_URL = 'postgresql://postgres:YOUR_DB_PASSWORD@127.0.0.1:5432/poly'
TABLE_NAME = "polydb"
ID_COL = "id"
SMILES_COL = "smiles"
CATEGORY_COL = "category"
TARGET_CATEGORIES = ("spermidine", "spermine")
# ----------------------------------------------------------------

# "自由胺氮"：排除酰胺/脲/氨基甲酸酯氮、磺酰胺氮、直接连芳香环的氮、氰基氮、硝基氮
FREE_AMINE_SMARTS = (
    "[#7;"
    "!$([#7]C(=O));"   # 排除酰胺/脲/氨基甲酸酯氮
    "!$([#7]S(=O));"   # 排除磺酰胺/亚磺酰胺氮
    "!$([#7]-a);"      # 排除直接挂在芳香环上的氮（含芳香环内氮本身）
    "!$([#7]#*);"      # 排除氰基氮
    "!$([#7](=O))"      # 排除硝基/亚硝基氮
    "]"
)
free_amine_pattern = Chem.MolFromSmarts(FREE_AMINE_SMARTS)
assert free_amine_pattern is not None, "SMARTS 规则解析失败，请检查语法"

# 用于诊断"具体是被哪类基团排除"的单项规则，方便在明细表里标注原因
DIAGNOSTIC_SMARTS = {
    "amide_or_urea_or_carbamate": "[#7]C(=O)",
    "sulfonamide": "[#7]S(=O)",
    "aromatic_attached": "[#7]-a",
    "nitrile": "[#7]#*",
    "nitro": "[#7](=O)",
}
diagnostic_patterns = {k: Chem.MolFromSmarts(v) for k, v in DIAGNOSTIC_SMARTS.items()}


def extract_chain(mol):
    """复刻 NCN.py 的 ExtratChain 逻辑：沿环-链连接键切开分子"""
    bonds = mol.GetBonds()
    rings = mol.GetRingInfo()
    bond_cut = []
    for bond in bonds:
        if not bond.IsInRing():
            bg = (bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
            for ring_atoms in rings.AtomRings():
                if set(bg) & set(ring_atoms):
                    bond_cut.append(bond.GetIdx())
                    break
    if not bond_cut:
        return [mol]  # 整个分子就是一条链（无环），当作一个碎片处理
    new = Chem.FragmentOnBonds(mol, list(set(bond_cut)))
    frags = Chem.GetMolFrags(new, asMols=True, sanitizeFrags=False)
    return list(frags)


def sanitize_frag(frag):
    try:
        Chem.SanitizeMol(frag, sanitizeOps=Chem.SANITIZE_ALL ^ Chem.SANITIZE_KEKULIZE, catchErrors=True)
    except Exception:
        pass
    return frag


def count_free_amine_in_fragment(frag):
    """对单个碎片，统计排除非真实胺氮后的自由胺氮个数"""
    frag = sanitize_frag(frag)
    return len(frag.GetSubstructMatches(free_amine_pattern))


def max_free_amine_across_fragments(mol):
    """取所有碎片中，自由胺氮个数的最大值（对应 NCN.py 的"任一碎片满足即命中"逻辑）"""
    try:
        frags = extract_chain(mol)
    except Exception:
        frags = [mol]
    best = 0
    for frag in frags:
        n = count_free_amine_in_fragment(frag)
        best = max(best, n)
    return best


def diagnose_reasons(mol):
    """对整个分子（不分片），标注它命中了哪些排除类别，用于明细表里说明原因"""
    reasons = []
    for name, pat in diagnostic_patterns.items():
        if mol.HasSubstructMatch(pat):
            reasons.append(name)
    return ";".join(reasons) if reasons else ""


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        f"SELECT {ID_COL}, {SMILES_COL}, {CATEGORY_COL} "
        f"FROM {TABLE_NAME} WHERE {CATEGORY_COL} = ANY(%s)",
        (list(TARGET_CATEGORIES),),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"共读取 {len(rows)} 条记录（spermidine + spermine）")

    total_by_cat = {c: 0 for c in TARGET_CATEGORIES}
    fail_by_cat = {c: 0 for c in TARGET_CATEGORIES}
    parse_failed = []
    mismatches = []

    for i, (rid, smiles, category) in enumerate(rows):
        total_by_cat[category] += 1
        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            parse_failed.append((rid, smiles, category))
            continue
        free_n = max_free_amine_across_fragments(mol)
        if free_n < 2:
            fail_by_cat[category] += 1
            reasons = diagnose_reasons(mol)
            mismatches.append((rid, category, free_n, reasons, smiles))
        if (i + 1) % 200 == 0:
            print(f"  已处理 {i + 1}/{len(rows)} ...")

    print("\n===== 汇总结果（完整版：排除酰胺+磺酰胺+芳香胺+氰基+硝基） =====")
    for c in TARGET_CATEGORIES:
        total = total_by_cat[c]
        fail = fail_by_cat[c]
        pct = (fail / total * 100) if total else 0
        print(f"{c:12s}: 总数 {total:5d}  排除后不再满足N>=2的记录数 {fail:5d}  ({pct:.1f}%)")

    if parse_failed:
        print(f"\nSMILES解析失败: {len(parse_failed)} 条")

    # 按触发原因做一个粗统计，方便看主要是哪类基团导致的
    from collections import Counter
    reason_counter = Counter()
    for _, _, _, reasons, _ in mismatches:
        for r in reasons.split(";"):
            if r:
                reason_counter[r] += 1
    print("\n触发排除原因分布（一条记录可能同时命中多个原因）：")
    for reason, cnt in reason_counter.most_common():
        print(f"  {reason:30s}: {cnt}")

    out_path = "/tmp/amide_misclassification_candidates_v2.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "category", "free_amine_n_after_exclusion", "trigger_reasons", "smiles"])
        writer.writerows(mismatches)
    print(f"\n疑似误判记录明细已写入: {out_path} (共 {len(mismatches)} 条)")


if __name__ == "__main__":
    main()
