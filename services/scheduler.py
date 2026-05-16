
import time
import logging

from config.settings import ENABLE_FACEBOOK_POSTING
from services.queue_manager import QueueManager
from services.facebook_publisher import FacebookPublisher
from services.priority_telegram_publisher import PriorityTelegramPublisher
from DB.db import db_execute

logger = logging.getLogger(__name__)

_queue = QueueManager()
_fb = FacebookPublisher()
_tg = PriorityTelegramPublisher()


def _publish_one(post: dict) -> None:
    """Publish a single queue item to all active channels and update its DB row."""

    post_id = post["id"]
    telegram_status = "pending"
    facebook_status = "pending"

    # ── Telegram ──────────────────────────────────────────────────────────────
    try:
        _tg.publish(post)
        telegram_status = "sent"
        logger.info(f"✅ Telegram sent  | id={post_id} | {post['title'][:60]}")
    except Exception as exc:
        telegram_status = "failed"
        logger.error(f"❌ Telegram error | id={post_id} | {exc}")

    # ── Facebook ──────────────────────────────────────────────────────────────
    if ENABLE_FACEBOOK_POSTING:
        try:
            success = _fb.publish(post)
            facebook_status = "sent" if success else "failed"
            if success:
                logger.info(f"✅ Facebook sent  | id={post_id}")
            else:
                logger.warning(f"⚠️  Facebook fail  | id={post_id}")
        except Exception as exc:
            facebook_status = "failed"
            logger.error(f"❌ Facebook error | id={post_id} | {exc}")

    # ── Single DB update ──────────────────────────────────────────────────────
    db_execute(
        """
        UPDATE news_queue
        SET
            status            = 'published',
            telegram_status   = %s,
            facebook_status   = %s,
            published_at      = NOW()
        WHERE id = %s
        """,
        (telegram_status, facebook_status, post_id),
    )


def publishing_worker() -> None:
    """
    Continuously drains the pending queue.

    • When items are present  → publish immediately, loop back right away.
    • When queue is empty     → sleep 5 s then poll again.

    This replaces the old time-gate approach (POST_INTERVAL_MINUTES) which
    caused articles to wait up to POST_INTERVAL_MINUTES * 60 seconds before
    being considered for publishing — the direct cause of the 8-hour delay.
    """
    logger.info("🚀 Publishing worker started (real-time mode)")

    while True:
        try:
            post = _queue.get_next_post()

            if post:
                _publish_one(post)
                # Don't sleep — check for the next item immediately.
                continue

        except Exception as exc:
            logger.error(f"⚠️  Publishing worker error: {exc}", exc_info=True)

        # Queue is empty (or an unexpected error occurred) — wait before retrying.
        time.sleep(5)
