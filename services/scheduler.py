import time
from config.settings import POST_INTERVAL_MINUTES, ENABLE_FACEBOOK_POSTING
from services.queue_manager import QueueManager
from services.facebook_publisher import FacebookPublisher
from DB.db import db_execute
from services.priority_telegram_publisher import PriorityTelegramPublisher


priority_tg = PriorityTelegramPublisher()
queue = QueueManager()
fb = FacebookPublisher()

LAST_POST_TIME = 0


def publishing_worker():
    global LAST_POST_TIME

    while True:

        time.sleep(5)

        now = time.time()

        if now - LAST_POST_TIME < POST_INTERVAL_MINUTES * 60:
            continue

        post = queue.get_next_post()

        if not post:
            continue

        # =====================
        # TELEGRAM ALREADY ACTIVE IN YOUR SYSTEM
        # =====================
        priority_tg.publish(post)
        db_execute("""
            UPDATE news_queue
            SET
                status='published',
                telegram_status='sent',
                published_at=NOW()
            WHERE id=%s
        """, (post["id"],))

        # =====================
        # FACEBOOK (DISABLED)
        # =====================

        if ENABLE_FACEBOOK_POSTING:

            success = fb.publish(post)

            if success:

                db_execute("""
                    UPDATE news_queue
                    SET facebook_status='sent'
                    WHERE id=%s
                """, (post["id"],))

            else:

                db_execute("""
                    UPDATE news_queue
                    SET facebook_status='failed'
                    WHERE id=%s
                """, (post["id"],))
        LAST_POST_TIME = now
