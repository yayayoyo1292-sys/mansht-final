import time
from DB.db import db_execute
from services.priority_engine import calculate_final_score


class QueueManager:

    def add_or_update_queue_item(self, article):

        scores = calculate_final_score(
            article["title"],
            article.get("content") or "",
            article["created_at"]
        )

        db_execute("""
            INSERT INTO news_queue (
                article_id,
                title,
                url,
                content,
                image_url,
                created_at,
                keyword_score,
                aging_score,
                ai_score,
                final_score,
                status,
                last_updated
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',NOW())
            ON CONFLICT (url) DO UPDATE SET
                keyword_score = EXCLUDED.keyword_score,
                aging_score = EXCLUDED.aging_score,
                ai_score = EXCLUDED.ai_score,
                final_score = EXCLUDED.final_score,
                image_url = EXCLUDED.image_url,
                last_updated = NOW()
        """, (
            article["article_id"],
            article["title"],
            article["url"],
            article.get("content"),
            article.get("image_url"),
            article["created_at"],
            scores["keyword_score"],
            scores["aging_score"],
            0,  # ai_score (مؤقت لو مش محسوب)
            scores["final_score"]
        ))

    def reorder_queue(self):
        db_execute("""
            UPDATE news_queue
            SET final_score = keyword_score + aging_score
        """)

    def get_next_post(self):

        return db_execute("""
            SELECT *
            FROM news_queue
            WHERE status = 'pending'
            ORDER BY
                final_score DESC,
                created_at ASC
            LIMIT 1
        """, fetch=True)