import logging
import os
 
import requests
from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
 
load_dotenv()
 
logger = logging.getLogger(__name__)
 
 
class FacebookPublisher:
 
    def __init__(self):
        self.webhook_url = os.getenv("MAKE_WEBHOOK_URL")
        if not self.webhook_url:
            logger.warning(
                "⚠️  MAKE_WEBHOOK_URL is not set — Facebook publishing is disabled"
            )
 
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _send_request(self, payload: dict) -> requests.Response:
        assert self.webhook_url is not None
        response = requests.post(self.webhook_url, json=payload, timeout=30)
        if response.status_code != 200:
            logger.error(
                f"Facebook webhook failed: {response.status_code} — {response.text[:200]}"
            )
            raise requests.RequestException(f"Bad response: {response.status_code}")
        return response
 
    def publish(self, post: dict) -> bool:
        if not self.webhook_url:
            logger.warning("Facebook publish skipped — no webhook URL configured")
            return False
 
        payload = {
            "message": f"📰 {post['title']}\n\n{(post.get('content') or '')[:500]}",
            "image_url": post.get("image_url"),
        }
 
        try:
            self._send_request(payload)
            logger.info(f"✅ Facebook publish success for post id={post['id']}")
            return True
        except Exception as exc:
            logger.error(f"❌ Facebook publish failed for post id={post['id']}: {exc}")
            return False
