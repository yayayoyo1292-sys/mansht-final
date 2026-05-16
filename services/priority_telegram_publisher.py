
import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("PRIORITY_TELEGRAM_BOT_TOKEN")
_CHAT_ID = os.getenv("PRIORITY_TELEGRAM_CHAT_ID")

_TELEGRAM_CAPTION_LIMIT = 1024


class PriorityTelegramPublisher:

    def __init__(self):
        if not _TOKEN or not _CHAT_ID:
            raise RuntimeError(
                "PRIORITY_TELEGRAM_BOT_TOKEN and PRIORITY_TELEGRAM_CHAT_ID "
                "must be set in the environment"
            )

    def _build_caption(self, post: dict) -> str:
        content = (post.get("content") or "")[:500]
        raw = f"📰 {post['title']}\n\n{content}\n\n🔗 {post['url']}"
        # Truncate to Telegram's hard limit
        return raw[:_TELEGRAM_CAPTION_LIMIT]

    def publish(self, post: dict) -> bool:
        """Publish *post* to the priority Telegram channel. Returns True on success."""
        caption = self._build_caption(post)
        image_url = post.get("image_url")

        try:
            if image_url:
                resp = requests.post(
                    f"https://api.telegram.org/bot{_TOKEN}/sendPhoto",
                    data={
                        "chat_id": _CHAT_ID,
                        "photo": image_url,
                        "caption": caption,
                    },
                    timeout=30,
                )
            else:
                resp = requests.post(
                    f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
                    data={
                        "chat_id": _CHAT_ID,
                        "text": caption,
                    },
                    timeout=30,
                )

            if resp.status_code != 200:
                logger.error(
                    f"❌ Telegram API error {resp.status_code}: {resp.text[:200]}"
                )
                return False

            logger.info(f"✅ PRIORITY POST SENT: {post['title'][:60]}")
            return True

        except Exception as exc:
            logger.error(f"❌ PRIORITY TELEGRAM ERROR: {exc}")
            return False
