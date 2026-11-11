#=====================================================
# 文件名：clean_dedup_csv.py
# 作用：读取 polydb_export_full.csv，按 smiles 去重
#       （同一 smiles 多条记录时保留 id 最小的那条），
#       输出一份新的干净 CSV，另外单独输出一份被删除的 id 清单
#       （这份 id 清单后面用来同步删除数据库里对应的行）
#
# 用法（脚本现在放在 clean/ 子目录下，用绝对路径读写，
#       所以不管你从哪个目录执行都没关系）：
#   cd /home/ubuntu/web/polydb2.0
#   ./venv/bin/python clean/clean_dedup_csv.py
# =====================================================

import pandas as pd

SRC = "/home/ubuntu/web/polydb2.0/data/polydb_export_full.csv"
CLEANED_OUT = "/home/ubuntu/web/polydb2.0/data/polydb_export_full_cleaned.csv"
REMOVED_IDS_OUT = "/home/ubuntu/web/polydb2.0/data/polydb_removed_duplicate_ids.csv"

df = pd.read_csv(SRC)

# 自动匹配 id / smiles 列名（不区分大小写），避免因为列名大小写猜错而出错
cols_lower = {c.lower(): c for c in df.columns}
if "id" not in cols_lower or "smiles" not in cols_lower:
    raise SystemExit(
        f"没找到 id 或 smiles 列，实际列名是：{list(df.columns)}\n"
        f"请把这份列表发回去，确认真正的列名。"
    )
id_col = cols_lower["id"]
smiles_col = cols_lower["smiles"]

print(f"原始行数：{len(df)}")

# 排除 smiles 为空的行不参与去重判断（避免把多个空值误判为“重复”）
has_smiles = df[smiles_col].notna()
no_smiles_df = df[~has_smiles]
with_smiles_df = df[has_smiles].copy()

# 按 id 升序排序后，同一 smiles 只保留第一条（即 id 最小的那条）
with_smiles_df = with_smiles_df.sort_values(id_col)
is_dup = with_smiles_df.duplicated(subset=[smiles_col], keep="first")

removed_ids = with_smiles_df.loc[is_dup, id_col]
kept_with_smiles_df = with_smiles_df.loc[~is_dup]

cleaned_df = pd.concat([kept_with_smiles_df, no_smiles_df]).sort_values(id_col)

print(f"发现重复（将删除）：{len(removed_ids)} 行")
print(f"清洗后行数：{len(cleaned_df)}")

cleaned_df.to_csv(CLEANED_OUT, index=False)
removed_ids.to_csv(REMOVED_IDS_OUT, index=False, header=[id_col])

print(f"已写出干净文件：{CLEANED_OUT}")
print(f"已写出被删除的id清单：{REMOVED_IDS_OUT}")
