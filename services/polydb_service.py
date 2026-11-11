#=====================================================
# 文件名：services/polydb_service.py
# 作用：PolyDB 数据库业务查询
# =====================================================

import os
import glob
import pandas as pd
from functools import lru_cache
from .db_service import query_df, query_scalar


@lru_cache(maxsize=1)
def build_image_index(image_dir: str = None) -> dict:
    if image_dir is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        image_dir = os.path.join(base, "ours_image")

    names = {}
    for path in glob.glob(os.path.join(image_dir, "*.png")):
        basename = os.path.basename(path)
        mol_name = basename.split("_")[0]
        names[mol_name] = path
    return names


@lru_cache(maxsize=1)
def load_reaction_conditions(file_path: str = None) -> dict:
    if file_path is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base, "data", "reaction_conditions.md")

    reaction_conditions = {}
    if not os.path.exists(file_path):
        return reaction_conditions

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().split('##')[1:]
        for section in content:
            lines = section.strip().split('\n')
            name = lines[0].strip()
            conditions = [line.strip() for line in lines[1:] if line.startswith('-')]
            reaction_conditions[name] = conditions
    return reaction_conditions


def advanced_search(category: str, extra_conditions: str,
                    selected_columns: list, page: int, page_size: int,
                    sort_by: str = '', sort_dir: str = 'asc'):
    ALLOWED_SORT = {
        'id', 'formula', 'mw', 'tpsa', 'logp', 'energy',
        'hba', 'hbd', 'rotb', 'sa', 'qed', 'pains', 'chembl_id',
        'smiles', 'name', 'category'
    }
    order_clause = ''
    if sort_by and sort_by in ALLOWED_SORT:
        direction = 'DESC' if sort_dir == 'desc' else 'ASC'
        order_clause = f'ORDER BY {sort_by} {direction} NULLS LAST'

    safe_cols = [c for c in selected_columns if c in ALLOWED_SORT]
    if not safe_cols:
        safe_cols = list(ALLOWED_SORT)

    col_str = ", ".join(safe_cols)

    if category == 'ALL':
        cat_sql = "category IN ('spermidine', 'spermine', 'other')"
        cat_params = []
    else:
        cat_sql = "category = %s"
        cat_params = [category]

    where = f"WHERE {cat_sql}"
    if extra_conditions:
        where += f" AND ({extra_conditions})"

    offset = (page - 1) * page_size
    count_sql = f"SELECT COUNT(*) FROM polydb {where}"

    #↓↓↓ 这里是唯一修改的地方：加入了 {order_clause} ↓↓↓
    data_sql = f"SELECT {col_str} FROM polydb {where} {order_clause} LIMIT %s OFFSET %s"

    total = query_scalar(count_sql, cat_params if cat_params else None)
    params = cat_params + [page_size, offset]
    df = query_df(data_sql, params)

    return df, total


def find_by_smiles(smiles: str) -> pd.DataFrame:
    sql = "SELECT * FROM polydb WHERE smiles = %s"
    return query_df(sql, (smiles,))


def find_by_names(name_list: list) -> pd.DataFrame:
    if not name_list:
        return pd.DataFrame()
    placeholders = ",".join(["%s"] * len(name_list))
    sql = f"SELECT * FROM polydb WHERE name IN ({placeholders})"
    return query_df(sql, name_list)


def search_similar_molecules(smiles_in: str, radius: int = 2, top_n: int = 30,
                              sim_min: float = 0.0, sim_max: float = 1.0,
                              threshold: float = 0.5) -> pd.DataFrame:
    from .db_service import get_engine
    from sqlalchemy import text

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(f"SET rdkit.tanimoto_threshold = {float(threshold)}"))
        df = pd.read_sql(text("""
            SELECT p.*,
                   tanimoto_sml(
                       morgan_fp,
                       morganbv_fp(mol_from_smiles(CAST(:smi AS cstring)), :r)
                   ) AS similarity
            FROM polydb p
            WHERE morgan_fp % morganbv_fp(mol_from_smiles(CAST(:smi AS cstring)), :r)
            ORDER BY similarity DESC
            LIMIT :top_n
        """), conn, params={"smi": smiles_in, "r": radius, "top_n": top_n})

    if df.empty:
        return df
    df = df[(df['similarity'] >= sim_min) & (df['similarity'] <= sim_max)]
    df = df.drop_duplicates(subset=['smiles'], keep='first')
    return df


def find_similar_by_names(name_list: list, query_smiles: str,
                           sim_min: float = 0.0, sim_max: float = 1.0) -> pd.DataFrame:
    from rdkit import Chem, DataStructs
    from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator

    df = find_by_names(name_list)
    if df.empty:
        return df

    fpgen = GetMorganGenerator(radius=2)
    mol_q = Chem.MolFromSmiles(query_smiles)
    if mol_q is None:
        return pd.DataFrame()
    fp_q = fpgen.GetFingerprint(mol_q)

    def fast_sim(smi):
        m = Chem.MolFromSmiles(smi)
        if m is None:
            return 0.0
        return DataStructs.FingerprintSimilarity(fp_q, fpgen.GetFingerprint(m))

    df['similar'] = df['smiles'].apply(fast_sim)
    df = df[(df['similar'] >= sim_min) & (df['similar'] <= sim_max)]
    return df.sort_values('similar', ascending=False)


def get_download_data_stream():
    from .db_service import get_engine
    from sqlalchemy import text

    def generate():
        yield "id,smiles\n"
        engine = get_engine()
        with engine.connect() as conn:
            offset = 0
            batch = 1000
            while True:
                rows = conn.execute(
                    text("SELECT id, smiles FROM polydb ORDER BY id LIMIT :lim OFFSET :off"),
                    {"lim": batch, "off": offset}
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    yield f"{row[0]},{row[1]}\n"
                offset += batch

    return generate()


def get_download_data() -> str:
    df = query_df("SELECT id, smiles FROM polydb")
    return df.to_csv(index=False)