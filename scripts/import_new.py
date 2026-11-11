import pandas as pd
import psycopg2

df = pd.read_csv('/home/ubuntu/web/polydb2.0/molecules_merged.csv')

# 重命名smi为smiles
if 'smi' in df.columns:
    df = df.rename(columns={'smi': 'smiles'})

# 连接数据库
conn = psycopg2.connect(
    'postgresql://postgres:YOUR_DB_PASSWORD@127.0.0.1:5432/poly'
)
cur = conn.cursor()

# 获取当前最大ID号
cur.execute("SELECT id FROM polydb ORDER BY id DESC LIMIT 1;")
max_id = cur.fetchone()[0]
print(f"当前最大ID: {max_id}")

# 生成新ID（在最大ID基础上递增）
prefix = max_id[:1]  # 取前缀字母
num = int(max_id[1:]) + 1  # 取数字部分+1
new_ids = [f"{prefix}{str(num+i).zfill(len(max_id)-1)}" for i in range(len(df))]
df['id'] = new_ids

# 只保留数据库中有的列
valid_cols = ['id','formula','smarts','mw','tpsa','logp','pka','charge',
              'energy','hba','hbd','rotb','sa','pains','chembl_id',
              'smiles','name','inchi_key','cas','category']
df = df[[c for c in valid_cols if c in df.columns]]

print(f"准备导入 {len(df)} 条")
print(f"新ID范围: {df['id'].iloc[0]} ~ {df['id'].iloc[-1]}")

success = 0
for _, row in df.iterrows():
    try:
        cols = list(row.index)
        vals = list(row.values)
        placeholders = ','.join(['%s'] * len(cols))
        col_str = ','.join(cols)
        sql = f"INSERT INTO polydb ({col_str}) VALUES ({placeholders})"
        cur.execute(sql, vals)
        success += 1
    except Exception as e:
        print(f"失败: {e}")
        conn.rollback()

conn.commit()
cur.close()
conn.close()
print(f"完成！成功导入 {success} 条")
