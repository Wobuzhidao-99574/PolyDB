import psycopg2
from rdkit import Chem
from rdkit.Chem import QED

conn = psycopg2.connect(
    'postgresql://postgres:YOUR_DB_PASSWORD@127.0.0.1:5432/poly'
)
cur = conn.cursor()

cur.execute("SELECT id, smiles FROM polydb")
rows = cur.fetchall()
print(f"共 {len(rows)} 条，开始计算QED...")

success = 0
fail = 0
for i, (mol_id, smi) in enumerate(rows):
    try:
        mol = Chem.MolFromSmiles(smi)
        if mol:
            qed_val = round(QED.qed(mol), 6)
            cur.execute("UPDATE polydb SET qed=%s WHERE id=%s", (qed_val, mol_id))
            success += 1
        else:
            fail += 1
    except:
        fail += 1
    if i % 10000 == 0:
        conn.commit()
        print(f"进度：{i}/{len(rows)}")

conn.commit()
cur.close()
conn.close()
print(f"完成！成功 {success} 条，失败 {fail} 条")
