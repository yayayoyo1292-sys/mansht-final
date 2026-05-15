import os
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = pool.ThreadedConnectionPool(minconn=2, maxconn=10, dsn=DATABASE_URL)
def get_conn():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing in .env")
    return psycopg2.connect(DATABASE_URL)

def db_execute(query, params=None, fetch=False):
    conn = _pool.getconn()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(query, params or ())

        result = None

        if fetch:
            result = cursor.fetchone()

        conn.commit()

        return result

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        _pool.putconn(conn)
