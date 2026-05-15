import os
import requests


class FacebookPublisher:
    def __init__(self):
        self.webhook_url = os.getenv("MAKE_WEBHOOK_URL")

    def publish(self, post):
        payload = {
            "message": f"📰 {post['title']}\n\n{post.get('content', '')[:500]}",
            "image_url": post.get("image_url")
        }
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=30)
            if response.status_code == 200:
                print("✅ MAKE → FACEBOOK SENT")
            else:
                print(f"❌ MAKE ERROR: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ MAKE EXCEPTION: {e}")
