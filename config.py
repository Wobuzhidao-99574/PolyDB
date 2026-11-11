import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", 'YOUR_SECRET_KEY')
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        'postgresql://postgres:YOUR_DB_PASSWORD@127.0.0.1:5432/poly'
    )
    PAGE_SIZE = 100
    SIMILARITY_TOP_N = 30
    SIMILARITY_RADIUS = 2