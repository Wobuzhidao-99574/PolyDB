# =====================================================
# 文件名：scripts/build_embeddings.py
# 作用：批量预计算 mol2vec 嵌入向量并写入 polydb 表
# 运行：python3 scripts/build_embeddings.py
# 特性：支持断点续跑，跳过已有向量的行
# =====================================================

import os
import sys
import time

# 把项目根目录加入路径，确保能 import services
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import numpy as np
from rdkit import Chem
from gensim.models import word2vec
from mol2vec.features import mol2alt_sentence, MolSentence, sentences2vec

# ── 配置 ──────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "dbname":   "poly",
    "user":     "postgres",
    "password": "",          # 填你的数据库密码
    "port":     5432,
}
MODEL_PATH = "data/mol2vec_model_300dim.pkl"
BATCH_SIZE = 500   # 每批处理条数，内存不足可调小到 200
# ──────────────────────────────────────────────────


def vec_to_pg(vec: np.ndarray) -> str:
    """把 numpy 向量转成 pgvector 接受的字符串格式 '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def main():
    # 1. 加载模型
    print(f"加载 mol2vec 模型: {MODEL_PATH}")
    t0 = time.time()
    model = word2vec.Word2Vec.load(MODEL_PATH)
    print(f"模型加载完成，耗时 {time.time()-t0:.1f}s，词汇量: {len(model.wv)}")

    # 2. 连接数据库
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    # 3. 查询待处理总数
    cur.execute("SELECT COUNT(*) FROM polydb WHERE mol2vec_emb IS NULL")
    total = cur.fetchone()[0]
    print(f"待处理分子数: {total}")
    if total == 0:
        print("全部已处理，无需重跑")
        return

    # 4. 分批读取并处理
    cur.execute("""
        SELECT id, smiles FROM polydb
        WHERE mol2vec_emb IS NULL
        ORDER BY id
    """)
    rows = cur.fetchall()

    success = 0
    skip    = 0
    updates = []

    print(f"开始处理，批大小={BATCH_SIZE}...")
    t_start = time.time()

    for i, (mol_id, smi) in enumerate(rows):

        # 解析 SMILES
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is None:
            skip += 1
            continue

        # 计算 mol2vec 向量
        try:
            sentence = MolSentence(mol2alt_sentence(mol, radius=1))
            vec = sentences2vec([sentence], model, unseen='UNK')[0]
            updates.append((vec_to_pg(vec), mol_id))
            success += 1
        except Exception as e:
            print(f"  [WARN] {mol_id} 计算失败: {e}")
            skip += 1
            continue

        # 批量写入
        if len(updates) >= BATCH_SIZE:
            cur.executemany(
                "UPDATE polydb SET mol2vec_emb = %s::vector WHERE id = %s",
                updates
            )
            conn.commit()
            updates.clear()

            elapsed = time.time() - t_start
            rate    = success / elapsed
            remain  = (total - i - 1) / rate if rate > 0 else 0
            print(f"  进度: {i+1}/{total} | 成功={success} 跳过={skip} "
                  f"| 速度={rate:.0f}条/s | 预计剩余={remain/60:.1f}min")

    # 处理最后不足一批的数据
    if updates:
        cur.executemany(
            "UPDATE polydb SET mol2vec_emb = %s::vector WHERE id = %s",
            updates
        )
        conn.commit()

    cur.close()
    conn.close()

    total_time = time.time() - t_start
    print(f"\n完成！成功={success} 跳过={skip} 总耗时={total_time/60:.1f}min")


if __name__ == "__main__":
    main()
