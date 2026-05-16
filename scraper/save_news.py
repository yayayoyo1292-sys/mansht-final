import time
import traceback
from datetime import datetime

from DB.db import db_execute
from ML.ai import classify_news
from services.date_filter import is_within_range
from services.queue_manager import QueueManager
from utils.logger import logger

queue = QueueManager()


def save_news(
    news: list[dict],
    template_config: dict,
    generate_image_fn,
) -> None:
    """
    Parameters
    ----------
    news              : list of dicts from extract_news()
    template_config   : TEMPLATE_CONFIG dict (for category validation)
    generate_image_fn : callable matching generate_post_image() signature
    """
    for item in news:
        try:
            category, confidence = classify_news(
                item["title"],
                content=item.get("content"),
            )

            # ── Handle unknown / low-confidence ──────────────────────────────
            if category is None:
                logger.warning(f"⚠️ Low confidence: {item['title']}")
                category   = "عام"
                confidence = 0.0

            if category not in template_config:
                category = "عام"

            # ── Insert into news table ────────────────────────────────────────
            result = db_execute(
                """
                INSERT INTO news (title, url, image, category, confidence, content)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                RETURNING id
                """,
                (
                    item["title"],
                    item["url"],
                    item["image"],
                    category,
                    confidence,
                    item.get("content"),
                ),
                fetch=True,
            )

            if not result:
                logger.warning(f"⚠️ Article already exists: {item['title']}")
                continue

            news_id = result["id"] if isinstance(result, dict) else result[0]

            if not news_id:
                logger.error("❌ No news_id returned from DB")
                continue

            logger.info(f"\n🟢 New article: {item['title']}")

            # ── Generate image (queue will handle publishing) ─────────────────
            image_url = generate_image_fn(
                item["title"],
                item["image"],
                news_id,
                item["url"],
                category,
                confidence,
                item.get("content"),
                send_to_telegram=False,
            )

            if not image_url:
                logger.error(f"❌ Image generation failed for: {item['title']}")
                continue

            # ── Enqueue for real-time publishing ──────────────────────────────
            article_date = datetime.utcnow()
            if is_within_range(article_date):
                queue.add_or_update_queue_item({
                    "article_id": news_id,
                    "title":      item["title"],
                    "url":        item["url"],
                    "content":    item.get("content"),
                    "image_url":  image_url,
                    "created_at": time.time(),
                })

            # Keep generated_image column in sync
            db_execute(
                """
                UPDATE news_queue
                SET image_url = %s, generated_image = %s
                WHERE article_id = %s
                """,
                (image_url, f"news_{news_id}.jpg", news_id),
            )

            # ── Save training data ────────────────────────────────────────────
            if confidence >= 0.65 and category != "عام":
                db_execute(
                    """
                    INSERT INTO confirmed_training (title, category, confidence)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (title) DO NOTHING
                    """,
                    (item["title"], category, confidence),
                )

        except Exception as exc:
            logger.error(f"❌ Save error: {exc}")
            traceback.print_exc()
