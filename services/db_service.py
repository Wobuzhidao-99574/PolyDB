import os
import psycopg2
import pandas as pd
from sqlalchemy import create_engine, text
from functools import lru_cache

@lru_cache(maxsize=1)
def get_engine():
    url = os.environ.get("DATABASE_URL", 'postgresql://postgres:YOUR_DB_PASSWORD@127.0.0.1:5432/poly')
    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)

def get_conn():
    url = os.environ.get("DATABASE_URL", 'postgresql://postgres:YOUR_DB_PASSWORD@127.0.0.1:5432/poly')
    return psycopg2.connect(url)

def query_df(sql: str, params=None) -> pd.DataFrame:
    # 直接用 psycopg2 connection，支援 %s 格式，避免 SQLAlchemy params 格式問題
    with get_conn() as conn:
        return pd.read_sql(sql, conn, params=params)

def query_scalar(sql: str, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return row[0] if row else 0
