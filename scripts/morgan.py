from rdkit import Chem
from rdkit.Chem import AllChem
import psycopg2

# 连接到数据库
conn = psycopg2.connect(
    dbname="poly",
    user="postgres",
    password='YOUR_DB_PASSWORD',
    host="localhost",
    port="5432"
)
cursor = conn.cursor()

# 获取所有分子的 SMILES 和 ID
cursor.execute("SELECT id, smiles FROM polydb")
rows = cursor.fetchall()
# 创建 MorganGenerator 实例
morgan_generator = AllChem.MorganGenerator(radius=2, nBits=2048)

# 计算 Morgan 指纹并更新数据库
for row in rows:
    mol_id, smiles = row
    mol = Chem.MolFromSmiles(smiles)
    if mol:
        fp = morgan_generator.GetFingerprint(mol)  # 使用 MorganGenerator 生成指纹
        fp_bytes = fp.ToBinary()  # 转换为二进制格式
        cursor.execute(
            "UPDATE polydb SET morgan_fp = %s WHERE id = %s",
            (fp_bytes, mol_id)
        )
    else:
        print(f"Invalid SMILES: {smiles}")
# 提交更改并关闭连接
conn.commit()
cursor.close()
conn.close()
