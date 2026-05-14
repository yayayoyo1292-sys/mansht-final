import requests
import os

from utils.logger import logger

TOKEN = os.getenv("PRIORITY_TELEGRAM_BOT_TOKEN")

CHAT_ID = os.getenv("PRIORITY_TELEGRAM_CHAT_ID")


class PriorityTelegramPublisher:

    def publish(self, post):
        try:
            caption = f"""
📰 {post['title']}

{(post.get('content') or '')[:500]}

🔗 {post['url']}
"""
            image_url = post.get("image_url")

            if image_url:
                # ← بعت صورة مع caption
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
                    data={
                        "chat_id": CHAT_ID,
                        "photo": image_url,
                        "caption": caption,
                    },
                    timeout=30
                )
            else:
                # ← fallback: نص فقط لو مفيش صورة
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    data={
                        "chat_id": CHAT_ID,
                        "text": caption
                    },
                    timeout=30
                )

            logger.info(f"PRIORITY POST SENT: {post['title']}")

        except Exception as e:
            logger.error(f"PRIORITY TELEGRAM ERROR: {e}")