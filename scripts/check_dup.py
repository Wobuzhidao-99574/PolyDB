import pandas as pd
import psycopg2

df = pd.read_csv('/home/ubuntu/web/polydb2.0/molecules_merged.csv')
smiles_list = df['smi'].dropna().tolist()

conn = psycopg2.connect('postgresql://postgres:YOUR_DB_PASSWORD@127.0.0.1:5432/poly')
cur = conn.cursor()

placeholders = ','.join(['%s'] * len(smiles_list))
cur.execute(f"SELECT smiles FROM polydb WHERE smiles IN ({placeholders})", smiles_list)
existing = [r[0] for r in cur.fetchall()]

print(f"CSV共 {len(df)} 条")
print(f"数据库已存在 {len(existing)} 条")
print(f"真正新增 {len(df) - len(existing)} 条")

cur.close()
conn.close()
