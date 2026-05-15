import os
import requests
import logging

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

logger = logging.getLogger(__name__)


class FacebookPublisher:

    def __init__(self):

        self.webhook_url = os.getenv("MAKE_WEBHOOK_URL")

        if not self.webhook_url:
            raise ValueError(
                "MAKE_WEBHOOK_URL is missing in environment variables"
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True
    )
    def _send_request(self, payload):

        response = requests.post(
            self.webhook_url,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:

            logger.error(
                f"Facebook webhook failed: "
                f"{response.status_code} - {response.text}"
            )

            raise requests.RequestException(
                f"Bad response: {response.status_code}"
            )

        return response

    def publish(self, post):

        payload = {
            "message": (
                f"📰 {post['title']}\n\n"
                f"{post.get('content', '')[:500]}"
            ),
            "image_url": post.get("image_url")
        }

        try:

            self._send_request(payload)

            logger.info(
                f"Facebook publish success for post {post['id']}"
            )

            return True

        except Exception as e:

            logger.exception(
                f"Facebook publish failed for post "
                f"{post['id']} : {e}"
            )

            return False
