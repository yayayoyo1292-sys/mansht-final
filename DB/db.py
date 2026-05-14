import os
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing in .env")
    return psycopg2.connect(DATABASE_URL)

def db_execute(query, params=None, fetch=False):
    conn = get_conn()
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
        cursor.close()
        conn.close()