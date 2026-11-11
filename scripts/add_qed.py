import pandas as pd
from rdkit import Chem
from rdkit.Chem import QED

# 读取CSV
df = pd.read_csv('/home/ubuntu/web/polydb2.0/molecules_merged.csv')

# 计算QED
def calc_qed(smi):
    try:
        mol = Chem.MolFromSmiles(smi)
        if mol:
            return round(QED.qed(mol), 3)
    except:
        pass
    return None

print("计算QED中...")
df['qed'] = df['smi'].apply(calc_qed)

# 把qed插入到smi后面
cols = list(df.columns)
smi_idx = cols.index('smi')
cols.insert(smi_idx + 1, cols.pop(cols.index('qed')))
df = df[cols]

# 保存
df.to_csv('/home/ubuntu/web/polydb2.0/molecules_merged.csv', index=False)
print("完成！前3行预览：")
print(df[['id','smi','qed']].head(3))
