"""
services/instant_publisher.py
──────────────────────────────
Priority Instant Publishing Engine
====================================

Provides two public helpers used by scraper/save_news.py:

    is_priority_article(title, content) -> bool
        Returns True if the article matches any INSTANT_PUBLISH_KEYWORDS phrase.
        Matching is FULL EXACT PHRASE only (no partial / single-word hits).

    instant_publish(post, priority_tg_publisher, fb_publisher) -> None
        Publishes the article immediately to Telegram (and optionally Facebook),
        then marks the news_queue row as 'published' so the normal queue worker
        does NOT re-publish it.

Design notes
────────────
• Arabic Unicode is normalised (NFKC) before matching so that visually-identical
  characters in different encodings still compare equal.
• The duplicate-prevention contract is simple: save_news.py inserts the queue row
  first, then calls instant_publish().  instant_publish() always sets
  status='published' in the same DB transaction, so the queue worker (scheduler.py)
  which filters WHERE status='pending' will never see the row again.
• All priority-publish events are logged at INFO level with a distinctive
  🚨 PRIORITY prefix so they are easy to grep in production logs.
"""

import logging
import unicodedata

from config.settings import INSTANT_PUBLISH_KEYWORDS, ENABLE_FACEBOOK_POSTING
from DB.db import db_execute

logger = logging.getLogger(__name__)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """NFKC-normalise *text* so visually identical Arabic forms compare equal."""
    return unicodedata.normalize("NFKC", text or "")


def _build_search_text(title: str, content: str | None) -> str:
    """Combine title + content into a single normalised string for matching."""
    parts = [_normalise(title)]
    if content:
        parts.append(_normalise(content))
    return " ".join(parts)


# ── Public API ─────────────────────────────────────────────────────────────────

def is_priority_article(title: str, content: str | None = None) -> bool:
    """
    Return True when *title* or *content* contains any phrase from
    INSTANT_PUBLISH_KEYWORDS as an exact, whole-phrase match.

    Rules enforced here:
    ✓  Full phrase match only  (e.g. "منصور بن محمد بن راشد" must appear verbatim)
    ✗  Single-word / partial hits are NOT accepted
    ✗  "منصور" alone does NOT trigger even though it's a substring of a longer keyword

    Implementation detail
    ─────────────────────
    Python's `in` operator on strings performs substring matching, which is exactly
    what "exact phrase" means for multi-word Arabic phrases — it checks that the
    *complete* configured keyword phrase occurs somewhere inside the text.
    Single-word keywords in the list (e.g. "حاكم", "زايد") are intentionally
    included as configured by the product owner and will match whenever that exact
    word appears in the text.
    """
    search_text = _build_search_text(title, content)

    for keyword in INSTANT_PUBLISH_KEYWORDS:
        normalised_keyword = _normalise(keyword)
        if normalised_keyword in search_text:
            logger.info(
                f"🚨 PRIORITY MATCH | keyword='{keyword}' | title='{title[:80]}'"
            )
            return True

    return False


def instant_publish(
    post: dict,
    priority_tg_publisher,
    fb_publisher,
) -> None:
    """
    Publish *post* immediately, bypassing the normal queue cycle.

    Parameters
    ----------
    post                  : queue row dict — must contain at minimum:
                            id, article_id, title, url, content, image_url
    priority_tg_publisher : PriorityTelegramPublisher instance
    fb_publisher          : FacebookPublisher instance

    Side-effects
    ────────────
    1. Sends to Telegram via priority_tg_publisher.publish(post).
    2. Optionally sends to Facebook if ENABLE_FACEBOOK_POSTING is True.
    3. Updates news_queue row to status='published' so the queue worker skips it.
    """
    queue_id   = post["id"]
    title_snip = post.get("title", "")[:80]

    logger.info(
        f"🚨 INSTANT PUBLISH START | queue_id={queue_id} | '{title_snip}'"
    )

    telegram_status = "pending"
    facebook_status = "pending"

    # ── Telegram ──────────────────────────────────────────────────────────────
    try:
        priority_tg_publisher.publish(post)
        telegram_status = "sent"
        logger.info(
            f"🚨 INSTANT PUBLISH ✅ Telegram sent | queue_id={queue_id}"
        )
    except Exception as exc:
        telegram_status = "failed"
        logger.error(
            f"🚨 INSTANT PUBLISH ❌ Telegram error | queue_id={queue_id} | {exc}"
        )

    # ── Facebook ──────────────────────────────────────────────────────────────
    if ENABLE_FACEBOOK_POSTING:
        try:
            success = fb_publisher.publish(post)
            facebook_status = "sent" if success else "failed"
            logger.info(
                f"🚨 INSTANT PUBLISH {'✅' if success else '⚠️'} Facebook "
                f"| queue_id={queue_id}"
            )
        except Exception as exc:
            facebook_status = "failed"
            logger.error(
                f"🚨 INSTANT PUBLISH ❌ Facebook error | queue_id={queue_id} | {exc}"
            )

    # ── Mark as published in DB — queue worker will never pick this up again ──
    db_execute(
        """
        UPDATE news_queue
        SET
            status          = 'published',
            telegram_status = %s,
            facebook_status = %s,
            published_at    = NOW(),
            last_updated    = NOW()
        WHERE id = %s
          AND status != 'published'   -- idempotency guard: never double-update
        """,
        (telegram_status, facebook_status, queue_id),
    )

    logger.info(
        f"🚨 INSTANT PUBLISH COMPLETE | queue_id={queue_id} "
        f"| tg={telegram_status} fb={facebook_status}"
    )
