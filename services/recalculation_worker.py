import time

from DB.db import get_conn
from services.priority_engine import calculate_aging_bonus


def recalculate_queue():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, created_at, keyword_score, ai_score
        FROM news_queue
        WHERE status='pending'
    """)

    rows = cur.fetchall()

    now = time.time()

    for row in rows:

        queue_id = row[0]
        created_at = row[1]
        keyword_score = row[2]
        ai_score = row[3]

        aging_score = calculate_aging_bonus(created_at, now)

        final_score = (
            keyword_score +
            aging_score +
            ai_score
        )

        cur.execute("""
            UPDATE news_queue
            SET
                aging_score=%s,
                final_score=%s,
                last_updated=NOW()
            WHERE id=%s
        """, (
            aging_score,
            final_score,
            queue_id
        ))

    conn.commit()

    cur.close()
    conn.close()


def recalculation_worker():

    while True:

        try:

            recalculate_queue()

            print("🔄 Queue recalculated")

        except Exception as e:

            print("❌ RECALC ERROR:", e)

        time.sleep(60)